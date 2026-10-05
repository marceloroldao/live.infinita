from pathlib import Path
import http.server,threading,json,time,subprocess
r=Path(__file__).resolve().parents[1]
p=r/'tests/godot_panel_delivery_008di_smoke.gd'
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        now=time.time()
        result={"schema":"live-infinita-nov-panel/v1","source":"native_renderer_journey","world_id":"fixture","generated_at_unix":now,
                "learning_status":{"world_id":"fixture","observed_at_unix":now,"completed_steps":27}}
        raw=json.dumps(result).encode()
        self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
engine='/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64'
try:
    run=subprocess.run([engine,'--headless','--audio-driver','Dummy','--path','/home/etbra/008bz-godot-test','--script',str(p),'--','--offline-tour','--panel-http=http://127.0.0.1:'+str(server.server_port)],capture_output=True,text=True,timeout=30)
    Path('/home/etbra/008di-http.log').write_text(run.stdout+run.stderr)
    Path('/home/etbra/008di-http.status').write_text(str(run.returncode))
    print(run.stdout+run.stderr,flush=True)
    if run.returncode or any(marker in run.stdout+run.stderr for marker in ['SCRIPT ERROR:', 'Parse Error:', 'Failed to load script','ERROR:']):
        raise SystemExit(1)
finally:server.shutdown()
