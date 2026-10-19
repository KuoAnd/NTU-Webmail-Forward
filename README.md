# webmail_forward

定期從 NTU Mail（POP3）收信，並透過 IMAP `APPEND` 直接寫入 Gmail。

Gmail 已停止支援以 POP3 收取其他信箱，這個腳本用來取代該功能。信件以原始內容寫入，寄件人、標頭、附件都保持不變，也不會因 SPF/DKIM 檢查被擋或被當成垃圾信。

- 只使用 Python 標準函式庫，不需要虛擬環境或安裝套件
- 以 POP3 `UIDL` 記錄已處理的信，並在寫入前用 Message-ID 檢查 Gmail 是否已有同一封信，避免重複匯入
- 預設不刪除 NTU 信箱中的信

## 檔案說明

| 檔案 | 說明 |
|---|---|
| `ntu2gmail.py` | 主程式 |
| `run.sh` | 安裝／移除／查看 cron 排程 |
| `config.example.ini` | 設定檔範本 |
| `config.ini` | 實際設定檔（含密碼，**不會**進 git） |
| `seen_uids.json` | 已處理信件的記錄（執行後自動產生，不進 git） |
| `ntu2gmail.log` | cron 執行紀錄（不進 git） |

## 事前準備

### 1. NTU Mail 帳號

依照[計中郵件軟體設定說明](https://jsc.cc.ntu.edu.tw/ntucc/email/mailsoftwaresetup.html)：

| 帳號類型 | POP3 伺服器 | Port |
|---|---|---|
| 學號帳號（學生、校友） | `msa.ntu.edu.tw` | 995（SSL） |
| 姓名縮寫帳號 | `ccms.ntu.edu.tw` | 995（SSL） |

學號帳號的使用者名稱**只填學號**（例如 `b12345678`），不要加 `@ntu.edu.tw`。

### 2. Gmail 應用程式密碼

1. 到 [Google 帳戶 → 安全性](https://myaccount.google.com/security) 開啟**兩步驟驗證**
2. 到 [應用程式密碼](https://myaccount.google.com/apppasswords) 產生一組 16 碼密碼

注意：

- **兩步驟驗證必須保持開啟**，關閉後應用程式密碼會全部失效
- 更改 Google 帳戶密碼也會讓應用程式密碼失效，需重新產生並更新 `config.ini`
- 程式用應用程式密碼登入 IMAP，不會觸發兩步驟驗證

## 安裝與設定

```bash
git clone git@github.com:<your-account>/webmail_forward.git ~/webmail_forward
cd ~/webmail_forward

cp config.example.ini config.ini
chmod 600 config.ini        # 必要：其他人可讀時程式會拒絕執行
vim config.ini
```

`config.ini` 範例：

```ini
[ntu]
host = msa.ntu.edu.tw
port = 995
user = b12345678
password = 你的NTU密碼

[gmail]
user = you@gmail.com
app_password = abcdefghijklmnop

[options]
mailbox = INBOX
delete_after_import = false
state_file = seen_uids.json
```

| 選項 | 說明 |
|---|---|
| `mailbox` | 寫入 Gmail 的位置。`INBOX` 為收件匣；也可填標籤名稱（例如 `NTU`），請使用英文 |
| `delete_after_import` | `true` 時，成功匯入後刪除 NTU 信箱中的信 |
| `state_file` | 已處理信件的記錄檔 |

值不需要加引號；應用程式密碼建議 16 碼連在一起寫。

## 執行

先用 dry-run 確認，不會寫入 Gmail：

```bash
./ntu2gmail.py --dry-run
```

確認無誤後擇一：

```bash
./ntu2gmail.py              # 匯入所有尚未處理的信（包含舊信）
./ntu2gmail.py --mark-seen  # 不匯入，只把目前的信標記為已處理，之後只收新信
```

其他參數：

```bash
./ntu2gmail.py -c /path/to/config.ini   # 指定設定檔
./ntu2gmail.py -v                       # 顯示除錯訊息
```

## 定期執行（cron）

```bash
./run.sh              # 安裝或更新排程（預設每 10 分鐘）
INTERVAL=5 ./run.sh   # 改為每 5 分鐘
./run.sh status       # 查看排程
./run.sh remove       # 移除排程
```

`run.sh` 只會增刪帶有 `# ntu2gmail` 標記的那一行，不影響其他 crontab 設定，重複執行也只會保留一行。

查看執行狀況：

```bash
tail -f ~/webmail_forward/ntu2gmail.log
```

注意：

- **crontab 只在安裝它的那台工作站上有效**。換工作站時，先在舊機器 `./run.sh remove`，再到新機器執行 `./run.sh`，避免兩台同時執行
- 程式有 lock 機制，上一次還沒跑完時，下一次會直接結束
- 本系工作站規範允許收信用途，但請勿把間隔設得過短

## 重新部署

若工作站重置或換機器：

1. `git clone` 本專案
2. 重新建立 `config.ini` 並 `chmod 600`
3. 執行 `./run.sh`

`seen_uids.json` 遺失也沒關係，程式會用 Message-ID 檢查 Gmail，已存在的信會跳過，不會重複匯入。

## 注意事項

- 以 IMAP `APPEND` 寫入的信**不會套用 Gmail 篩選器與垃圾信過濾**；需要分類時可改 `mailbox` 寫入指定標籤
- 匯入的信為未讀狀態，時間為信件原始的 `Date`
- `config.ini` 以明碼儲存密碼，請確認權限為 `600`，並且不要 commit

## 疑難排解

| 錯誤訊息 | 可能原因 |
|---|---|
| `-ERR Logon failure: unknown user name or bad password.` | POP3 伺服器設錯（應為 `msa.ntu.edu.tw` 而非 `mail.ntu.edu.tw`）或使用者名稱加了 `@ntu.edu.tw` |
| `-ERR [AUTH] Authentication failed.` | NTU 密碼錯誤，請先用 webmail 確認 |
| `IMAP4.error: ... Invalid credentials` | Gmail 應用程式密碼錯誤或已失效（關閉了兩步驟驗證、改過帳戶密碼） |
| `config.ini is readable by others` | 執行 `chmod 600 config.ini` |
| `another run is in progress` | 上一次仍在執行，屬正常狀況 |
