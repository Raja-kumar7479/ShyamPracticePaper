import os, sys, time, resource

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
os.chdir(f'{ROOT}/user_app'); sys.path.insert(0, f'{ROOT}/user_app')
from routes.exam_platform.placement_exam_portal.coding_portal.services import code_executor, docker_runner
from routes.exam_platform.placement_exam_portal.practice_coding.services import code_executor as practice_executor

results = []
def check(name, ok, detail=''):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))

CASE = [{'input_text': '2 3\n', 'expected_output': '5'}]
PROGRAMS = {
    'python': "a, b = map(int, input().split())\nprint(a + b)\n",
    'javascript': "const [a, b] = require('fs').readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\nconsole.log(a + b);\n",
    'c': "#include <stdio.h>\nint main(){int a,b;scanf(\"%d %d\",&a,&b);printf(\"%d\\n\",a+b);return 0;}\n",
    'cpp': "#include <bits/stdc++.h>\nusing namespace std;\nint main(){int a,b;cin>>a>>b;cout<<a+b<<endl;return 0;}\n",
    'java': "import java.util.*;\npublic class Main{public static void main(String[] x){Scanner s=new Scanner(System.in);int a=s.nextInt(),b=s.nextInt();System.out.println(a+b);}}\n",
    'csharp': "using System;\npublic class Program{public static void Main(string[] x){var p=Console.ReadLine().Split(' ');Console.WriteLine(int.Parse(p[0])+int.Parse(p[1]));}}\n",
}

def first(result):
    return result.cases[0] if result.cases else None

print('\n== every language still runs inside the hardened sandbox ==')
st = docker_runner.docker_status(max_age=0)
check('Docker is running and the judge image is present', st['docker'] and st['image'], str(st))
for lang, code in PROGRAMS.items():
    t = time.time(); r = code_executor.execute(code, lang, CASE); c = first(r)
    check(f'{lang}: compiles, runs and passes', r.compiled and c is not None and c.status == 'PASS', f"{time.time() - t:.1f}s status={c.status if c else r.error}")
r = practice_executor.execute(PROGRAMS['python'], 'python', CASE)
check('the practice judge uses the same sandbox and passes', first(r) is not None and first(r).status == 'PASS')

print('\n== isolation ==')
def py(code, expected=None, time_limit=None):
    return code_executor.execute(code, 'python', [{'input_text': '', 'expected_output': expected or 'x'}], time_limit=time_limit)
r = py("import os\nprint(os.getuid())\n", expected=str(os.getuid()))
c = first(r)
check('the program does not run as root', c is not None and c.output.strip() not in ('', '0'), c.output.strip() if c else r.error)
r = py("try:\n    open('/etc/spp_probe', 'w').write('x'); print('WROTE')\nexcept Exception as e:\n    print('BLOCKED')\n", expected='BLOCKED')
check('the root filesystem is read-only', first(r) is not None and first(r).status == 'PASS', first(r).output[:40] if first(r) else r.error)
r = py("import socket\ntry:\n    socket.create_connection(('1.1.1.1', 53), timeout=3); print('NET')\nexcept Exception:\n    print('BLOCKED')\n", expected='BLOCKED')
check('the network is blocked', first(r) is not None and first(r).status == 'PASS', first(r).output[:40] if first(r) else r.error)
r = py("import os\ntry:\n    os.setuid(0); print('ROOT')\nexcept Exception:\n    print('BLOCKED')\n", expected='BLOCKED')
check('the program cannot become root', first(r) is not None and first(r).status == 'PASS', first(r).output[:40] if first(r) else r.error)

print('\n== resource limits ==')
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
t = time.time()
r = py("import sys\nchunk = 'A' * 1048576\nfor _ in range(600):\n    sys.stdout.write(chunk)\n", time_limit=10)
took = time.time() - t
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
grew_mb = (after - before) / (1024 * 1024) if sys.platform == 'darwin' else (after - before) / 1024
c = first(r)
check('a program printing 600 MB is stopped with "Output limit exceeded"', c is not None and c.status == 'RE' and 'Output limit' in (c.error or ''), f"{c.status if c else r.error} {(c.error or '')[:50] if c else ''} in {took:.1f}s")
check('the judge process memory stays flat during that (it grew 560 MB before)', grew_mb < 60, f'grew {grew_mb:.0f} MB')
check('the shown output is truncated, not the whole dump', c is not None and len(c.output) <= 25000, str(len(c.output)) if c else '')
r = py("try:\n    with open('big.bin', 'wb') as f:\n        for _ in range(200):\n            f.write(b'x' * 1048576)\n    print('WROTE')\nexcept Exception as e:\n    print('BLOCKED')\n", expected='BLOCKED')
c = first(r)
check('a program cannot write a huge file to the host', c is not None and (c.status == 'PASS' or c.status == 'RE'), f"{c.status} {c.output[:20]!r}" if c else r.error)
r = py("import os, time\nn = 0\ntry:\n    while True:\n        if os.fork() == 0:\n            time.sleep(3); os._exit(0)\n        n += 1\nexcept Exception:\n    print('STOPPED' if n < 200 else 'MANY')\n", expected='STOPPED', time_limit=8)
c = first(r)
check('a fork bomb is stopped by the process limit', c is not None and 'STOPPED' in c.output, c.output[:30] if c else r.error)
r = py("x = []\ntry:\n    while True:\n        x.append(bytearray(10485760))\nexcept MemoryError:\n    print('CAUGHT')\n", expected='never', time_limit=8)
c = first(r)
check('a memory bomb is killed', c is not None and c.status in ('RE', 'FAIL', 'TLE'), c.status if c else r.error)
t = time.time(); r = py("while True:\n    pass\n", time_limit=2); c = first(r)
check('an infinite loop ends as Time Limit Exceeded', c is not None and c.status == 'TLE' and time.time() - t < 20, f"{c.status if c else r.error} in {time.time() - t:.1f}s")
r = code_executor.execute("int main(){ return 1 }", 'c', CASE)
check('a compile error is reported as such', not r.compiled and bool(r.error), (r.error or '')[:60])
import subprocess
left = subprocess.run(['docker', 'ps', '-a', '--filter', 'name=cjr-', '--format', '{{.Names}}'], capture_output=True, text=True).stdout.strip()
check('no containers are left behind', left == '', left[:80])

import subprocess as _sp
import re
_probe = '''
import logging, sys
logging.disable(logging.CRITICAL)
sys.path.insert(0, sys.argv[1])
from routes.exam_platform.placement_exam_portal.coding_portal.services import code_executor
r = code_executor.execute("print(1)\\n", "python", [{"input_text": "", "expected_output": "1"}])
print("DOWN", r.compiled, len(r.cases), r.error or "")
'''
_out = _sp.run([sys.executable, '-c', _probe, f'{ROOT}/user_app'], capture_output=True, text=True, timeout=120,
               env=dict(os.environ, JUDGE_IMAGE='codejudge-runner:does-not-exist'), cwd=f'{ROOT}/user_app').stdout
_got = (re.search(r'DOWN (.*)', _out) or [None, ''])[1]
check('when the judge cannot start at all (no image, Docker down) a run is reported as unavailable, not as the student\'s runtime error',
      _got.startswith('True 0 ') and 'not available' in _got, _got[:120])

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
