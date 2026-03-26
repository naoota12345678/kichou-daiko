const SITES = {
  amazon: {
    domain: ".amazon.co.jp",
    url: "https://www.amazon.co.jp",
    label: "Amazon",
  },
  rakuten: {
    domain: ".rakuten.co.jp",
    url: "https://www.rakuten.co.jp",
    label: "楽天市場",
  },
  yahoo: {
    domain: ".yahoo.co.jp",
    url: "https://shopping.yahoo.co.jp",
    label: "Yahoo",
  },
};

const API_URL = "https://scraper-api-274739552175.asia-northeast1.run.app";
const APP_URL = "https://dentyo.romu.ai";

// ページロード時にcookie状態チェック
document.addEventListener("DOMContentLoaded", async () => {
  for (const [key, site] of Object.entries(SITES)) {
    const el = document.getElementById(`status-${key}`);
    try {
      const cookies = await chrome.cookies.getAll({ domain: site.domain });
      if (cookies.length > 0) {
        el.textContent = `${cookies.length}個のcookie`;
        el.className = "status ok";
      } else {
        el.textContent = "未ログイン";
      }
    } catch {
      el.textContent = "エラー";
      el.className = "status error";
    }
  }
});

document.getElementById("send-all").addEventListener("click", async () => {
  const btn = document.getElementById("send-all");
  const msg = document.getElementById("message");
  btn.disabled = true;
  btn.textContent = "送信中...";
  msg.textContent = "";

  // Firebase ID tokenを取得（電帳ツールのページからメッセージで取得）
  let idToken = null;
  try {
    // 電帳ツールのタブを探す
    const tabs = await chrome.tabs.query({ url: `${APP_URL}/*` });
    if (tabs.length > 0) {
      const response = await chrome.tabs.sendMessage(tabs[0].id, {
        type: "GET_ID_TOKEN",
      });
      idToken = response?.idToken;
    }
  } catch {
    // タブがない場合はlocalStorageから試行
  }

  if (!idToken) {
    msg.textContent = "電帳ツール(dentyo.romu.ai)を開いてログインしてください";
    msg.style.color = "#dc2626";
    btn.disabled = false;
    btn.textContent = "セッションを送信";
    return;
  }

  // 各サイトのcookieを収集して送信
  let successCount = 0;
  for (const [key, site] of Object.entries(SITES)) {
    const el = document.getElementById(`status-${key}`);
    try {
      const cookies = await chrome.cookies.getAll({ domain: site.domain });
      if (cookies.length === 0) {
        el.textContent = "未ログイン - スキップ";
        continue;
      }

      // cookieをPlaywright storage_state形式に変換
      const cookieData = cookies.map((c) => ({
        name: c.name,
        value: c.value,
        domain: c.domain,
        path: c.path,
        expires: c.expirationDate || -1,
        httpOnly: c.httpOnly,
        secure: c.secure,
        sameSite: c.sameSite === "no_restriction" ? "None" : c.sameSite === "lax" ? "Lax" : "Strict",
      }));

      const res = await fetch(`${API_URL}/api/save-session`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${idToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          site: key,
          cookies: cookieData,
        }),
      });

      if (res.ok) {
        el.textContent = "送信完了";
        el.className = "status ok";
        successCount++;
      } else {
        el.textContent = "送信失敗";
        el.className = "status error";
      }
    } catch (e) {
      el.textContent = "エラー";
      el.className = "status error";
    }
  }

  msg.textContent = `${successCount}サイトのセッションを保存しました`;
  msg.style.color = "#16a34a";
  btn.disabled = false;
  btn.textContent = "セッションを送信";
});
