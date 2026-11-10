/* Read-only balance request. Credentials stay inside this short-lived worker. */
'use strict';
const {createRequire}=require('node:module');
const path=require('node:path');
const https=require('node:https');

async function balanceRequest(key) {
  return new Promise((resolve,reject)=>{
    const request=https.request('https://api.deepseek.com/user/balance',{
      method:'GET',headers:{Authorization:'Bearer '+key,Accept:'application/json'}
    },response=>{
      if(response.statusCode!==200){response.resume();resolve({error_code:response.statusCode===401||response.statusCode===403?'auth':'unavailable'});return;}
      let size=0;const chunks=[];
      response.on('data',chunk=>{size+=chunk.length;if(size>65536){request.destroy();reject(new Error('size'));}else chunks.push(chunk);});
      response.on('error',reject);
      response.on('end',()=>{
        try {
          const data=JSON.parse(Buffer.concat(chunks).toString('utf8'));
          // Explicit projection, never return headers, credentials, arbitrary strings or errors.
          const money=x=>typeof x==='string' && /^-?(?:0|[1-9]\d{0,14})(?:\.\d{1,12})?$/.test(x)?x:null;
          const rows=Array.isArray(data.balance_infos)?data.balance_infos.slice(0,3):[];
          resolve({is_available:typeof data.is_available==='boolean'?data.is_available:null,
            balance_infos:rows.map(x=>({currency:['CNY','USD'].includes(x?.currency)?x.currency:null,
              total_balance:money(x?.total_balance),granted_balance:money(x?.granted_balance),topped_up_balance:money(x?.topped_up_balance)}))});
        }catch{resolve({error_code:'invalid'});}
      });
    });
    // No redirects, retries, inference endpoints or custom destinations.
    request.setTimeout(10000,()=>request.destroy(new Error('timeout')));
    request.on('error',reject);request.end();
  });
}

async function main(){
  try {
    const base=path.join(path.dirname(process.execPath),'resources','app.asar','dsh','package.json');
    const load=createRequire(base);
    const {Context}=load('@deepseek-ai/cordis');
    const {LocalCredentialProvider}=load('@deepseek-ai/dsh-credentials-local');
    const provider=new LocalCredentialProvider(new Context(),{watch:false});
    // Queries must never perform legacy credential migration or write settings.
    provider.migrateFlatDocument=async()=>{throw new Error('migration disabled');};
    provider.warnIgnoredKeys=()=>{};
    await provider.loadInitial();
    const stored=provider.values.has('DEEPSEEK_API_KEY')?await provider.resolve('DEEPSEEK_API_KEY'):null;
    const key=stored?.value || process.env.DEEPSEEK_API_KEY;
    if(typeof key!=='string'||!key||key.length>4096||/[\r\n]/.test(key))return {error_code:'missing_credentials'};
    return await balanceRequest(key);
  }catch{return {error_code:'network'};}
}

if(require.main===module)main().then(value=>process.stdout.write(JSON.stringify(value)));
module.exports={balanceRequest};
