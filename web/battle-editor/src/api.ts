let token='';
export class ApiError extends Error {code:string;details:any;status:number;constructor(status:number,body:any){super(body?.error?.message||`服务请求失败 (${status})`);this.status=status;this.code=body?.error?.code;this.details=body?.error?.details;}}
export async function api<T=any>(path:string,method='GET',data?:any):Promise<T> {
 const res=await fetch(`/api${path}`,{method,headers:{...(token?{'X-Editor-Token':token}:{}),...(data===undefined?{}:{'Content-Type':'application/json'})},body:data===undefined?undefined:JSON.stringify(data)});
 const body=await res.json();if(!res.ok)throw new ApiError(res.status,body);return body;
}
export async function session(){const result=await api('/session');token=result.token;return result;}

/** Upload only to the authenticated loopback editor; no base64 JSON expansion. */
export async function apiImage(blob:Blob,mime:string,signal?:AbortSignal):Promise<any> {
 const res=await fetch('/api/import-image',{method:'POST',headers:{'Content-Type':mime,...(token?{'X-Editor-Token':token}:{})},body:blob,signal,credentials:'same-origin'});
 const body=await res.json();if(!res.ok)throw new ApiError(res.status,body);return body;
}

/** Card artwork uses the same authenticated session as JSON, without putting its token in a URL. */
export async function apiPNG(path:string,signal?:AbortSignal):Promise<{blob:Blob;portraitSource:string|null}> {
 if(!/^\/api\/(?!\/)/.test(path)||path.includes('\\'))throw new Error('卡图地址必须来自本地服务。');
 const res=await fetch(path,{method:'GET',headers:token?{'X-Editor-Token':token}:{},signal,credentials:'same-origin'});
 if(!res.ok){let body:any;try{body=await res.json();}catch{}throw new ApiError(res.status,body);}
 if(res.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!=='image/png')throw new Error('卡图服务返回了无法识别的图片格式。');
 const blob=await res.blob();if(!blob.size)throw new Error('卡图服务返回了空图片。');
 return {blob,portraitSource:res.headers.get('X-Editor-Card-Portrait-Source')??res.headers.get('X-Editor-NP-Portrait-Source')};
}
