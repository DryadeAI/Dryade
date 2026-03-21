// One-off script to generate PWA icons from favicon.svg
import sharp from 'sharp';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const svgInput = readFileSync(resolve(__dirname, '../public/favicon.svg'));
const outDir = resolve(__dirname, '../public/icons');

async function generateIcon(size, filename) {
  await sharp(svgInput)
    .resize(size, size)
    .png()
    .toFile(resolve(outDir, filename));
  console.log(`Generated ${filename} (${size}x${size})`);
}

async function generateMaskableIcon(size, filename) {
  // Maskable: scale icon to 80% and center on dark background
  const iconSize = Math.round(size * 0.8);
  const padding = Math.round((size - iconSize) / 2);

  const resizedIcon = await sharp(svgInput)
    .resize(iconSize, iconSize)
    .png()
    .toBuffer();

  await sharp({
    create: {
      width: size,
      height: size,
      channels: 4,
      background: { r: 10, g: 10, b: 11, alpha: 1 } // #0a0a0b
    }
  })
    .composite([{ input: resizedIcon, left: padding, top: padding }])
    .png()
    .toFile(resolve(outDir, filename));
  console.log(`Generated ${filename} (${size}x${size} maskable)`);
}

await generateIcon(192, 'icon-192x192.png');
await generateIcon(512, 'icon-512x512.png');
await generateMaskableIcon(192, 'icon-maskable-192x192.png');
await generateMaskableIcon(512, 'icon-maskable-512x512.png');
await generateIcon(180, 'apple-touch-icon.png');

console.log('All PWA icons generated.');
