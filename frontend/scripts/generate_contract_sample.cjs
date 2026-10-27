const fs = require('fs');
const zlib = require('zlib');
function crc32(buf){let c=0xFFFFFFFF;for(let i=0;i<buf.length;i++){c^=buf[i];for(let j=0;j<8;j++){c=(c&1)?((c>>>1)^0xEDB88320):(c>>>1);}}return(c^0xFFFFFFFF)>>>0;}
function mc(t,d){const l=Buffer.alloc(4);l.writeUInt32BE(d.length);const tb=Buffer.from(t);const cr=crc32(Buffer.concat([tb,d]));const cb=Buffer.alloc(4);cb.writeUInt32BE(cr);return Buffer.concat([l,tb,d,cb]);}
const w=1280,h=720,s=Buffer.from([137,80,78,71,13,10,26,10]);
const ih=Buffer.alloc(13);ih.writeUInt32BE(w,0);ih.writeUInt32BE(h,4);ih[8]=8;ih[9]=2;
const raw=Buffer.alloc((w*3+1)*h);
for(let y=0;y<h;y++){raw[y*(w*3+1)]=0;for(let x=0;x<w;x++){const i=y*(w*3+1)+1+x*3;if(y>500){raw[i]=139;raw[i+1]=115;raw[i+2]=85;}else{raw[i]=223;raw[i+1]=231;raw[i+2]=237;}}}
const png=Buffer.concat([s,mc('IHDR',ih),mc('IDAT',zlib.deflateSync(raw)),mc('IEND',Buffer.alloc(0))]);
fs.writeFileSync('/mnt/c/Users/admin/Documents/Vigilens/frontend/src/fixtures/contract/contract-sample.png',png);
console.log('done');
