"""Login-link-protected HTTP and WebSocket proxy for a personal Colab preview."""
import asyncio
import hmac
import os
from http.cookies import SimpleCookie

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

UPSTREAM = os.environ.get("MPT_BACKEND", "http://127.0.0.1:8501").rstrip("/")
SECRET = os.environ["MPT_SESSION_SECRET"]
LOGIN_TOKEN = os.environ["MPT_LOGIN_TOKEN"]
PORT = int(os.environ.get("MPT_PROXY_PORT", "8765"))
COOKIE_NAME = "mpt_private_session"
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}
WS_HEADERS = {"sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol"}

def safe_equal(a, b):
    return hmac.compare_digest(a or "", b)

def headers_to_origin(headers, *, websocket=False):
    forbidden = HOP_BY_HOP | (WS_HEADERS if websocket else set())
    hdrs = {k: v for k, v in headers.items() if k.lower() not in forbidden}
    hdrs["Host"] = UPSTREAM.split("://", 1)[1]
    if "Origin" in hdrs:
        hdrs["Origin"] = UPSTREAM
    if "Cookie" in hdrs:
        cookies = SimpleCookie()
        try:
            cookies.load(hdrs["Cookie"])
            if COOKIE_NAME in cookies:
                del cookies[COOKIE_NAME]
            if cookies:
                hdrs["Cookie"] = "; ".join(f"{k}={m.value}" for k, m in cookies.items())
            else:
                del hdrs["Cookie"]
        except Exception:
            del hdrs["Cookie"]
    return hdrs

async def relay(source, destination):
    async for msg in source:
        if msg.type == WSMsgType.TEXT:
            await destination.send_str(msg.data)
        elif msg.type == WSMsgType.BINARY:
            await destination.send_bytes(msg.data)
        elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
            break

async def handle(request):
    if request.path == "/__mpt_private_login":
        if not safe_equal(request.query.get("token", ""), LOGIN_TOKEN):
            return web.Response(status=403, text="Enlace incorrecto. Vuelve a Colab.",
                                headers={"Cache-Control": "no-store"})
        response = web.HTTPFound("/")
        response.set_cookie(COOKIE_NAME, SECRET, secure=True,
                            httponly=True, samesite="Lax", max_age=4 * 3600)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        raise response

    if not safe_equal(request.cookies.get(COOKIE_NAME), SECRET):
        return web.Response(status=401,
                            text="Acceso privado. Abre el enlace completo generado en Google Colab.",
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    url = UPSTREAM + str(request.rel_url)
    session = request.app["session"]
    if request.headers.get("Upgrade", "").lower() == "websocket":
        protocols = [p.strip() for p in request.headers.get("Sec-WebSocket-Protocol", "").split(",") if p.strip()]
        ws_backend = await session.ws_connect(
            url, headers=headers_to_origin(request.headers, websocket=True),
            protocols=protocols, autoping=True, max_msg_size=0
        )
        negotiated = [ws_backend.protocol] if ws_backend.protocol else []
        ws_front = web.WebSocketResponse(protocols=negotiated, autoping=True, max_msg_size=0)
        await ws_front.prepare(request)
        tasks = {asyncio.create_task(relay(ws_front, ws_backend)),
                 asyncio.create_task(relay(ws_backend, ws_front))}
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await ws_backend.close()
        await ws_front.close()
        for task in done:
            if task.exception():
                print("Websocket relay:", repr(task.exception()), flush=True)
        return ws_front

    async with session.request(
        request.method, url, headers=headers_to_origin(request.headers),
        data=request.content.iter_chunked(65536) if request.can_read_body else None,
        allow_redirects=False, auto_decompress=False
    ) as upstream_resp:
        out_headers = {k: v for k, v in upstream_resp.headers.items() if k.lower() not in HOP_BY_HOP}
        out_headers["Cache-Control"] = out_headers.get("Cache-Control", "private, no-store")
        out = web.StreamResponse(status=upstream_resp.status, headers=out_headers)
        await out.prepare(request)
        async for data in upstream_resp.content.iter_chunked(65536):
            await out.write(data)
        await out.write_eof()
        return out

async def session_context(app):
    async with ClientSession(timeout=ClientTimeout(total=None), auto_decompress=False, trust_env=False) as session:
        app["session"] = session
        yield

app = web.Application(client_max_size=512 * 1024 ** 2)
app.cleanup_ctx.append(session_context)
app.router.add_route("*", "/{tail:.*}", handle)
web.run_app(app, host="127.0.0.1", port=PORT, print=None, access_log=None)
