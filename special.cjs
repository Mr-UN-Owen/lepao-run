const crypto = require("node:crypto");
const K = Buffer.from("Wet2C8d34f62ndi3"), IV = Buffer.from("K6iv85jBD8jgf32D"), SK = "rDJiNB9j7vD2";
const enc = s => { const c = crypto.createCipheriv("aes-128-cbc", K, IV); return Buffer.concat([c.update(s,"utf8"), c.final()]).toString("base64"); };
const dec = b => { const d = crypto.createDecipheriv("aes-128-cbc", K, IV); return Buffer.concat([d.update(Buffer.from(b,"base64")), d.final()]).toString("utf8"); };
const sign = p => crypto.createHash("md5").update(Object.keys(p).sort().map(k=>k+p[k]).join("")+SK,"utf8").digest("hex");
const r6 = () => String(Math.floor(Math.random()*1e6)+1e6).slice(1,7);
const UA = "Mozilla/5.0 (Linux; Android 10; Redmi Note 7) AppleWebKit/537.36 Chrome/142.0 Mobile Safari/537.36 XWEB/1420283 MMWEBID/2837 MicroMessenger/8.0.77.3160 WeChat/arm64 MiniProgramEnv/android";
const REF = "https://servicewechat.com/wxb2043232183dac7f/13/page-frame.html";
async function call(path, extra) {
  const p = { uid:"", token:"", school_id:"", term_id:0, course_id:0, class_id:0, student_num:"", card_id:"", ...extra, timestamp:Math.floor(Date.now()/1000), version:1, nonce:r6(), ostype:5 };
  p.sign = sign(p);
  const body = "ostype=5&data=" + encodeURIComponent(enc(JSON.stringify(p)));
  const r = await fetch("https://api2.lptiyu.com"+path, { method:"POST", headers:{ "content-length":String(Buffer.byteLength(body)), "content-type":"application/x-www-form-urlencoded", charset:"utf-8", referer:REF, "user-agent":UA, "accept-encoding":"gzip, deflate" }, body, signal:AbortSignal.timeout(12000) });
  const t = await r.text();
  let j; try { j = JSON.parse(t); } catch { return "HTTP"+r.status+" "+t.slice(0,80); }
  if (j.status===1 && typeof j.data==="string") { try { j.dec = JSON.parse(dec(j.data)); delete j.data; } catch {} }
  return JSON.stringify(j).slice(0,300);
}
(async () => {
  for (const sid of ["0","-1","all","*","1,2"]) {
    console.log("school_id="+sid.padEnd(5), "→", await call("/v3/api.php/WpLogin/getSchoolInfo", { school_id: sid }));
    await new Promise(r=>setTimeout(r,300));
  }
})();
