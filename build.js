const fs = require('fs');
const path = require('path');

const srcDir = path.join(__dirname, 'dashboard', 'frontend');
const distDir = path.join(__dirname, 'dist');

function copyRecursiveSync(src, dest) {
  const exists = fs.existsSync(src);
  const stats = exists && fs.statSync(src);
  const isDirectory = exists && stats.isDirectory();
  if (isDirectory) {
    if (!fs.existsSync(dest)) {
      fs.mkdirSync(dest, { recursive: true });
    }
    fs.readdirSync(src).forEach((childItemName) => {
      copyRecursiveSync(path.join(src, childItemName), path.join(dest, childItemName));
    });
  } else {
    fs.copyFileSync(src, dest);
  }
}

console.log('[BUILD] Cleaning dist directory...');
if (fs.existsSync(distDir)) {
  fs.rmSync(distDir, { recursive: true, force: true });
}
fs.mkdirSync(distDir, { recursive: true });

console.log(`[BUILD] Copying frontend assets from ${srcDir} to ${distDir}...`);
copyRecursiveSync(srcDir, distDir);

// Đảm bảo file _redirects có trong dist
const redirectsSrc = path.join(srcDir, '_redirects');
const redirectsDest = path.join(distDir, '_redirects');
if (fs.existsSync(redirectsSrc)) {
  fs.copyFileSync(redirectsSrc, redirectsDest);
} else {
  fs.writeFileSync(redirectsDest, '/*  /index.html  200\n');
}

console.log('[BUILD] Production build complete successfully! Output directory: dist');
