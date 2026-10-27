// Generate contract sample image
const fs = require('fs');
const path = require('path');

// Create a minimal valid PNG (1280x720) - simplified approach using zlib
// Actually easier to just create with node and write
const { createCanvas } = require('canvas');
const canvas = createCanvas(1280, 720);
const ctx = canvas.getContext('2d');

ctx.fillStyle = '#dfe7ed';
ctx.fillRect(0, 0, 1280, 720);
ctx.fillStyle = '#8b7355';
ctx.fillRect(0, 500, 1280, 220);
ctx.fillStyle = '#1e3a8a';
ctx.font = '20px Arial';
ctx.fillText('SYNTHETIC - contract test', 10, 30);

// person-1 no helmet, vest on
ctx.fillStyle = '#d4a574';
ctx.beginPath(); ctx.ellipse(480, 356, 30, 35, 0, 0, Math.PI*2); ctx.fill();
ctx.fillStyle = '#2563eb';
ctx.fillRect(455, 391, 50, 80);
ctx.fillStyle = '#f59e0b';
ctx.fillRect(455, 391, 50, 40);
ctx.fillStyle = '#8b4513';
ctx.beginPath(); ctx.ellipse(480, 318, 22, 28, 0, 0, Math.PI*2); ctx.fill();

// person-2 helmet and vest on
ctx.fillStyle = '#c68642';
ctx.beginPath(); ctx.ellipse(972, 356, 28, 33, 0, 0, Math.PI*2); ctx.fill();
ctx.fillStyle = '#16a34a';
ctx.fillRect(950, 389, 44, 75);
ctx.fillStyle = '#f59e0b';
ctx.fillRect(950, 389, 44, 40);
ctx.fillStyle = '#fbbf24';
ctx.beginPath(); ctx.ellipse(972, 308, 26, 16, 0, 0, Math.PI*2); ctx.fill();

// person-3 helmet on, vest partly hidden
ctx.fillStyle = '#b8860b';
ctx.beginPath(); ctx.ellipse(256, 360, 26, 31, 0, 0, Math.PI*2); ctx.fill();
ctx.fillStyle = '#7c3aed';
ctx.fillRect(236, 391, 40, 70);
ctx.fillStyle = '#f59e0b';
ctx.fillRect(236, 391, 25, 30);
ctx.fillStyle = '#fbbf24';
ctx.beginPath(); ctx.ellipse(256, 316, 24, 14, 0, 0, Math.PI*2); ctx.fill();

// person-4 helmet and vest on
ctx.fillStyle = '#a0522d';
ctx.beginPath(); ctx.ellipse(691, 180, 24, 29, 0, 0, Math.PI*2); ctx.fill();
ctx.fillStyle = '#dc2626';
ctx.fillRect(673, 209, 36, 65);
ctx.fillStyle = '#f59e0b';
ctx.fillRect(673, 209, 36, 35);
ctx.fillStyle = '#fbbf24';
ctx.beginPath(); ctx.ellipse(691, 138, 22, 13, 0, 0, Math.PI*2); ctx.fill();

const out = canvas.toBuffer('image/png');
fs.writeFileSync(path.join(__dirname, '../src/fixtures/contract/contract-sample.png'), out);
console.log('done');
