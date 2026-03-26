// 電帳ツール(dentyo.romu.ai)のページに注入されるcontent script
// Chrome拡張のpopupからのメッセージに応答してFirebase ID tokenを返す

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "GET_ID_TOKEN") {
    // ページのlocalStorageやindexedDBからFirebase tokenを取得するのは困難なので、
    // カスタムイベントを使ってページ内のJSと通信する
    window.postMessage({ type: "DENTYO_GET_TOKEN" }, "*");

    const handler = (event) => {
      if (event.data?.type === "DENTYO_TOKEN_RESPONSE") {
        window.removeEventListener("message", handler);
        sendResponse({ idToken: event.data.idToken });
      }
    };
    window.addEventListener("message", handler);

    // 3秒でタイムアウト
    setTimeout(() => {
      window.removeEventListener("message", handler);
      sendResponse({ idToken: null });
    }, 3000);

    return true; // 非同期レスポンス
  }
});
