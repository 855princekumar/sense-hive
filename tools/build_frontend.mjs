// Build SenseHive's browser code into version-1.0/static (committed):
//   frontend/*.jsx         -> static/<name>.js     (esbuild: JSX compiled ahead of time, minified)
//   frontend/input.css     -> static/sensehive.css (Tailwind: only the classes in use, EdgeShell palette)
//   react, react-dom       -> static/vendor/react.js (esbuild bundle of tools/react_globals.js,
//                             exact versions from package-lock.json; React 19 has no UMD files)
// and write static/SHA256SUMS. `--check` rebuilds into a temporary folder and
// fails when the committed files differ (CI runs it), so what ships is exactly
// what the sources produce. Nothing is loaded from a CDN at run time.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const check = process.argv.includes('--check');
const target = join(root, 'version-1.0', 'static');
const out = check ? mkdtempSync(join(tmpdir(), 'sensehive-static-')) : target;
const bin = (name) => join(root, 'node_modules', '.bin', process.platform === 'win32' ? `${name}.cmd` : name);
const run = (cmd, args) => execFileSync(cmd, args, { cwd: root, stdio: ['ignore', 'pipe', 'inherit'], shell: process.platform === 'win32' });

mkdirSync(join(out, 'vendor'), { recursive: true });
for (const f of readdirSync(join(root, 'frontend')).filter((f) => /\.jsx?$/.test(f))) {
  run(bin('esbuild'), [join('frontend', f), '--loader:.jsx=jsx', '--jsx-factory=React.createElement',
    '--jsx-fragment=React.Fragment', '--target=es2018', '--minify', '--legal-comments=none',
    `--outfile=${join(out, f.replace(/\.jsx?$/, '.js'))}`]);
}
run(bin('tailwindcss'), ['-c', 'tailwind.config.js', '-i', join('frontend', 'input.css'),
  '-o', join(out, 'sensehive.css'), '--minify']);
run(bin('esbuild'), [join('tools', 'react_globals.js'), '--bundle', '--format=iife', '--target=es2018', '--minify',
  '--legal-comments=none', '--define:process.env.NODE_ENV="production"', `--outfile=${join(out, 'vendor', 'react.js')}`]);

const files = [];
const walk = (d) => readdirSync(d, { withFileTypes: true }).forEach((e) =>
  e.isDirectory() ? walk(join(d, e.name)) : e.name !== 'SHA256SUMS' && files.push(join(d, e.name)));
walk(out);
const sums = files.map((f) => `${createHash('sha256').update(readFileSync(f)).digest('hex')}  ${relative(out, f).replace(/\\/g, '/')}`)
  .sort((a, b) => a.slice(66).localeCompare(b.slice(66))).join('\n') + '\n';
writeFileSync(join(out, 'SHA256SUMS'), sums);

if (check) {
  let committed = '';
  try { committed = readFileSync(join(target, 'SHA256SUMS'), 'utf8').replace(/\r\n/g, '\n'); } catch {}
  rmSync(out, { recursive: true, force: true });
  if (committed !== sums) {
    console.error('version-1.0/static is out of date with frontend/: run `npm run build` and commit.');
    process.exit(1);
  }
  console.log('version-1.0/static matches the sources');
} else {
  console.log(`built ${files.length} files into ${relative(root, out)}`);
}
