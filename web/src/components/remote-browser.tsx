"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface RemoteBrowserProps {
  wsUrl: string;
  onComplete: (items: any[], uploadedFiles: string[]) => void;
  onError: (message: string) => void;
}

export function RemoteBrowser({ wsUrl, onComplete, onError }: RemoteBrowserProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<string>("connecting");
  const statusRef = useRef("connecting");
  const [connected, setConnected] = useState(false);
  const [mobileInput, setMobileInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const BROWSER_WIDTH = 900;
  const BROWSER_HEIGHT = 900;

  useEffect(() => {
    if (!wsUrl) return;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (event) => {
      if (event.data instanceof Blob) {
        // JPEGフレーム → canvasに描画
        const img = new Image();
        const url = URL.createObjectURL(event.data);
        img.onload = () => {
          const canvas = canvasRef.current;
          if (canvas) {
            const ctx = canvas.getContext("2d");
            if (ctx) {
              ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            }
          }
          URL.revokeObjectURL(url);
        };
        img.src = url;
      } else {
        // JSONメッセージ
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "status") {
            setStatus(msg.status);
            statusRef.current = msg.status;
            if (msg.status === "ready" && msg.jobId) {
              // ジョブ作成済み → polling開始可能にする
              onComplete([], []);
            }
            if (msg.status === "complete") {
              onComplete(msg.items || [], msg.uploadedFiles || []);
            }
          } else if (msg.type === "error") {
            onError(msg.message);
          }
        } catch {
          // ignore
        }
      }
    };

    ws.onerror = () => {
      // スクレイピング開始後の切断はエラーではない
      const s = statusRef.current;
      if (s === "complete" || s === "scraping" || s === "ready" || s === "downloading_receipts") return;
      onError("WebSocket接続エラー");
    };

    ws.onclose = () => {
      setConnected(false);
    };

    // アプリ復帰時に自動でfocusInputを送信
    const handleVisibility = () => {
      if (document.visibilityState === "visible" && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "focusInput" }));
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    // WebSocketキープアライブ（30秒ごと）
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      clearInterval(pingInterval);
      ws.close();
    };
  }, [wsUrl, onComplete, onError]);

  // マウス座標をブラウザviewportに変換
  const getScaledCoords = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement> | React.TouchEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return { x: 0, y: 0 };

      const rect = canvas.getBoundingClientRect();
      let clientX: number, clientY: number;

      if ("touches" in e) {
        const touch = e.touches[0] || e.changedTouches[0];
        clientX = touch.clientX;
        clientY = touch.clientY;
      } else {
        clientX = e.clientX;
        clientY = e.clientY;
      }

      const x = Math.round(((clientX - rect.left) / rect.width) * BROWSER_WIDTH);
      const y = Math.round(((clientY - rect.top) / rect.height) * BROWSER_HEIGHT);
      return { x, y };
    },
    []
  );

  const sendMessage = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const { x, y } = getScaledCoords(e);
      sendMessage({ type: "click", x, y });
    },
    [getScaledCoords, sendMessage]
  );

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      const { x, y } = getScaledCoords(e);
      sendMessage({ type: "click", x, y });
    },
    [getScaledCoords, sendMessage]
  );

  const handleWheel = useCallback(
    (e: React.WheelEvent<HTMLCanvasElement>) => {
      const { x, y } = getScaledCoords(e);
      sendMessage({ type: "scroll", x, y, deltaX: e.deltaX, deltaY: e.deltaY });
    },
    [getScaledCoords, sendMessage]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      sendMessage({ type: "key", key: e.key, event: "keyDown" });
    },
    [sendMessage]
  );

  const handleKeyUp = useCallback(
    (e: React.KeyboardEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      sendMessage({ type: "key", key: e.key, event: "keyUp" });
    },
    [sendMessage]
  );

  const sendText = useCallback(
    (text: string) => {
      sendMessage({ type: "insertText", text });
    },
    [sendMessage]
  );

  const handleSendAndEnter = useCallback(() => {
    if (mobileInput) {
      sendText(mobileInput);
    }
    setTimeout(() => {
      sendMessage({ type: "key", key: "Enter", event: "keyDown" });
      sendMessage({ type: "key", key: "Enter", event: "keyUp" });
    }, 100);
    setMobileInput("");
  }, [mobileInput, sendText, sendMessage]);

  const handleSendText = useCallback(() => {
    if (mobileInput) {
      sendText(mobileInput);
      setMobileInput("");
    }
  }, [mobileInput, sendText]);

  const handleMobileTab = useCallback(() => {
    if (mobileInput) {
      sendText(mobileInput);
      setMobileInput("");
    }
    setTimeout(() => {
      sendMessage({ type: "key", key: "Tab", event: "keyDown" });
    }, 100);
  }, [mobileInput, sendText, sendMessage]);

  const handleMobileBackspace = useCallback(() => {
    sendMessage({ type: "key", key: "Backspace", event: "keyDown" });
  }, [sendMessage]);

  const handleFocusInput = useCallback(() => {
    sendMessage({ type: "focusInput" });
  }, [sendMessage]);

  const statusText: Record<string, string> = {
    connecting: "接続中...",
    starting: "ブラウザ起動中...",
    ready: "ログインしてください",
    scraping: "注文データ取得中...",
    complete: "完了！",
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>リモートブラウザ</span>
          <span
            className={`text-sm font-normal ${
              status === "complete"
                ? "text-green-600"
                : status === "scraping"
                ? "text-blue-600"
                : "text-muted-foreground"
            }`}
          >
            {statusText[status] || status}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-center">
        <div className="relative w-full">
          <canvas
            ref={canvasRef}
            width={BROWSER_WIDTH}
            height={BROWSER_HEIGHT}
            tabIndex={0}
            onClick={handleClick}
            onTouchEnd={handleTouchEnd}
            onWheel={handleWheel}
            onKeyDown={handleKeyDown}
            onKeyUp={handleKeyUp}
            className="w-full cursor-pointer rounded-lg border shadow-lg focus:outline-none focus:ring-2 focus:ring-primary"
            style={{ touchAction: "none" }}
          />
          {status === "starting" && (
            <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-black/50">
              <p className="text-lg text-white">ブラウザ起動中...</p>
            </div>
          )}
        </div>

        {/* モバイル用テキスト入力 */}
        <div className="mt-3 w-full space-y-2">
          <Input
            ref={inputRef}
            value={mobileInput}
            onChange={(e) => setMobileInput(e.target.value)}
            placeholder="ここに入力してください"
            className="w-full text-base h-14 text-lg"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
          />
          <div className="grid grid-cols-5 gap-2">
            <Button onClick={handleSendText} variant="secondary" className="h-12">
              入力
            </Button>
            <Button onClick={handleSendAndEnter} className="h-12">
              入力+決定
            </Button>
            <Button variant="outline" onClick={handleFocusInput} className="h-12">
              欄選択
            </Button>
            <Button variant="outline" onClick={handleMobileTab} className="h-12">
              次の欄
            </Button>
            <Button variant="outline" onClick={handleMobileBackspace} className="h-12">
              削除
            </Button>
          </div>
          <p className="text-xs text-muted-foreground text-center">
            文字を入力 →「入力」で送信 →「入力+決定」でログイン
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
