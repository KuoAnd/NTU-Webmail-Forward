#!/usr/bin/env python3
"""Fetch mail from NTU Mail over POP3 and import it into Gmail via IMAP APPEND.

Meant to be run periodically (e.g. from cron). Only the standard library is used.
"""
import argparse
import configparser
import email
import email.policy
import email.utils
import fcntl
import imaplib
import json
import logging
import os
import poplib
import re
import stat
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(BASE_DIR, "config.ini")

log = logging.getLogger("ntu2gmail")


def load_config(path):
    if not os.path.exists(path):
        sys.exit(f"config not found: {path} (copy config.example.ini and fill it in)")
    mode = os.stat(path).st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        sys.exit(f"{path} is readable by others; run: chmod 600 {path}")
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(path, encoding="utf-8")
    return cfg


def load_state(path):
    try:
        with open(path) as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_state(path, seen):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(seen), f)
    os.replace(tmp, path)


def imap_quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_all_mail(gm):
    """Return the name of Gmail's "All Mail" folder (its name depends on UI language)."""
    typ, data = gm.list()
    if typ != "OK":
        return None
    for line in data:
        line = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
        if "\\All" in line:
            m = re.search(r'"([^"]+)"\s*$', line) or re.search(r"(\S+)\s*$", line)
            if m:
                return m.group(1)
    return None


def already_in_gmail(gm, msgid):
    """Check whether a message with this Message-ID already exists in Gmail."""
    if not msgid or '"' in msgid or "\\" in msgid:
        return False
    typ, data = gm.search(None, "X-GM-RAW", imap_quote(f"rfc822msgid:{msgid.strip('<> ')}"))
    return typ == "OK" and bool(data and data[0].split())


def internal_date(msg):
    try:
        dt = email.utils.parsedate_to_datetime(msg["Date"])
        return imaplib.Time2Internaldate(dt)
    except Exception:
        return imaplib.Time2Internaldate(time.time())


def run(cfg, args):
    pop_cfg, gm_cfg, opt = cfg["ntu"], cfg["gmail"], cfg["options"] if cfg.has_section("options") else {}
    mailbox = opt.get("mailbox", "INBOX")
    delete_after = str(opt.get("delete_after_import", "false")).lower() in ("1", "true", "yes")
    state_path = os.path.join(BASE_DIR, opt.get("state_file", "seen_uids.json"))

    seen = load_state(state_path)

    pop = poplib.POP3_SSL(pop_cfg["host"], int(pop_cfg.get("port", 995)), timeout=60)
    pop.user(pop_cfg["user"])
    pop.pass_(pop_cfg["password"])

    uidl = [line.decode().split() for line in pop.uidl()[1]]
    new = [(num, uid) for num, uid in uidl if uid not in seen]
    log.info("NTU mailbox: %d messages, %d new", len(uidl), len(new))

    if args.mark_seen:
        seen.update(uid for _, uid in uidl)
        save_state(state_path, seen)
        log.info("marked all %d messages as seen without importing", len(uidl))
        pop.quit()
        return

    if not new:
        pop.quit()
        return

    gm = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=60)
    gm.login(gm_cfg["user"], gm_cfg["app_password"])
    all_mail = find_all_mail(gm)
    if all_mail:
        gm.select(imap_quote(all_mail), readonly=True)

    imported = 0
    try:
        for num, uid in new:
            raw = b"\r\n".join(pop.retr(num)[1]) + b"\r\n"
            msg = email.message_from_bytes(raw, policy=email.policy.compat32)
            subject = msg.get("Subject", "")

            if all_mail and already_in_gmail(gm, msg.get("Message-ID")):
                log.info("skip (already in Gmail): uid=%s %s", uid, subject)
                if args.dry_run:
                    continue
            elif args.dry_run:
                log.info("[dry-run] would import uid=%s %s", uid, subject)
                continue
            else:
                typ, resp = gm.append(imap_quote(mailbox), "", internal_date(msg), raw)
                if typ != "OK":
                    log.error("APPEND failed for uid=%s: %s", uid, resp)
                    break
                imported += 1
                log.info("imported uid=%s %s", uid, subject)

            seen.add(uid)
            save_state(state_path, seen)
            if delete_after:
                pop.dele(num)
    finally:
        gm.logout()
        pop.quit()  # deletions (if any) are committed here

    log.info("done: %d imported", imported)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-c", "--config", default=DEFAULT_CONFIG)
    ap.add_argument("--dry-run", action="store_true", help="show what would be imported")
    ap.add_argument("--mark-seen", action="store_true",
                    help="record all current NTU messages as seen without importing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config(args.config)

    # Prevent overlapping runs when a previous cron job is still going.
    lock = open(os.path.join(BASE_DIR, ".ntu2gmail.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.info("another run is in progress, exiting")
        return

    try:
        run(cfg, args)
    except (poplib.error_proto, imaplib.IMAP4.error, OSError) as e:
        log.error("%s: %s", type(e).__name__, e)
        sys.exit(1)


if __name__ == "__main__":
    main()
