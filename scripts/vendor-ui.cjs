const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const vendor=path.join(root,'web/vendor');fs.mkdirSync(vendor,{recursive:true});
fs.copyFileSync(path.join(root,'node_modules/gsap/dist/gsap.min.js'),path.join(vendor,'gsap.min.js'));
fs.copyFileSync(path.join(root,'node_modules/gsap/dist/Flip.min.js'),path.join(vendor,'Flip.min.js'));
for(const file of ['umd/photoswipe.umd.min.js','photoswipe.css'])fs.copyFileSync(path.join(root,'node_modules/photoswipe/dist',file),path.join(vendor,path.basename(file)));
fs.copyFileSync(path.join(root,'node_modules/photoswipe/LICENSE'),path.join(vendor,'photoswipe-LICENSE.txt'));
for(const family of ['manrope','literata']){
  const base=path.join(root,'node_modules/@fontsource-variable',family);
  for(const subset of ['cyrillic','latin'])fs.copyFileSync(path.join(base,'files',`${family}-${subset}-wght-normal.woff2`),path.join(vendor,`${family}-${subset}.woff2`));
  fs.copyFileSync(path.join(base,'LICENSE'),path.join(vendor,`${family}-LICENSE.txt`));
}
console.log('Vendored pinned GSAP/Flip, PhotoSwipe and Cyrillic/Latin font subsets.');
