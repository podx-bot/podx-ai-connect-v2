import time
from typing import Any
import httpx
class WhatsAppService:
 RETRYABLE_HTTP_STATUS={408,429,500,502,503,504};MAX_AUDIO_BYTES=16*1024*1024
 def __init__(self,access_token,phone_number_id,api_version,max_attempts=3,retry_delay_seconds=.5):
  self.access_token=access_token;self.phone_number_id=phone_number_id;self.api_version=api_version;self.max_attempts=max(1,int(max_attempts));self.retry_delay_seconds=max(0,float(retry_delay_seconds));self._http_client=httpx.Client(timeout=httpx.Timeout(connect=3,read=60,write=60,pool=3),limits=httpx.Limits(max_keepalive_connections=10,max_connections=20,keepalive_expiry=30))
 def is_configured(self):return bool(self.access_token and self.phone_number_id and self.api_version)
 def _auth_headers(self):return {'Authorization':f'Bearer {self.access_token}'}
 def _messages_url(self):return f'https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages'
 def _send_with_retry(self,payload):
  if not self.is_configured():return {'success':False,'status':'NOT_CONFIGURED','attempts':0}
  headers={**self._auth_headers(),'Content-Type':'application/json'};last={}
  for attempt in range(1,self.max_attempts+1):
   last=self._send_once(self._messages_url(),headers,payload);last['attempts']=attempt
   if last.get('success') or not last.get('retryable') or attempt>=self.max_attempts:return last
   if self.retry_delay_seconds:time.sleep(self.retry_delay_seconds*attempt)
  return last
 def _mobile(self,m):return ''.join(c for c in str(m) if c.isdigit())
 def send_text_message(self,m,message):return self._send_with_retry({'messaging_product':'whatsapp','recipient_type':'individual','to':self._mobile(m),'type':'text','text':{'preview_url':False,'body':str(message).strip()}})
 def _send_media_by_id(self,m,kind,media_id,caption=''):
  mid=str(media_id or '').strip()
  if not mid:return {'success':False,'status':'MEDIA_ID_MISSING','attempts':0}
  obj={'id':mid};cap=str(caption or '').strip()
  if cap:obj['caption']=cap[:1024]
  return self._send_with_retry({'messaging_product':'whatsapp','recipient_type':'individual','to':self._mobile(m),'type':kind,kind:obj})
 def send_image_by_id(self,m,media_id,caption=''):return self._send_media_by_id(m,'image',media_id,caption)
 def send_video_by_id(self,m,media_id,caption=''):return self._send_media_by_id(m,'video',media_id,caption)
 def send_reply_buttons(self,m,body,buttons):
  actions=[]
  for item in buttons[:3]:
   bid=str(item.get('id') or '').strip()[:256];title=str(item.get('title') or '').strip()[:20]
   if bid and title:actions.append({'type':'reply','reply':{'id':bid,'title':title}})
  if not actions:return self.send_text_message(m,body)
  return self._send_with_retry({'messaging_product':'whatsapp','recipient_type':'individual','to':self._mobile(m),'type':'interactive','interactive':{'type':'button','body':{'text':str(body).strip()},'action':{'buttons':actions}}})
 def upload_audio(self,audio_bytes,mime_type='audio/ogg',file_name='podx-reply.ogg'):
  if not self.is_configured():return {'success':False,'status':'NOT_CONFIGURED'}
  if not audio_bytes:return {'success':False,'status':'EMPTY_AUDIO'}
  if len(audio_bytes)>self.MAX_AUDIO_BYTES:return {'success':False,'status':'AUDIO_TOO_LARGE','actual_bytes':len(audio_bytes),'max_bytes':self.MAX_AUDIO_BYTES}
  try:
   r=self._http_client.post(f'https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/media',headers=self._auth_headers(),data={'messaging_product':'whatsapp'},files={'file':(str(file_name),audio_bytes,str(mime_type or 'audio/ogg'))},timeout=60);body=self._safe_json(r)
   if not 200<=r.status_code<300:return {'success':False,'status':'MEDIA_UPLOAD_HTTP_ERROR','http_status':r.status_code,'provider_response':body}
   mid=str(body.get('id','')).strip();return {'success':True,'status':'UPLOADED','media_id':mid,'provider_response':body} if mid else {'success':False,'status':'MEDIA_ID_MISSING','provider_response':body}
  except httpx.TimeoutException:return {'success':False,'status':'MEDIA_UPLOAD_TIMEOUT'}
  except httpx.HTTPError as e:return {'success':False,'status':'MEDIA_UPLOAD_NETWORK_ERROR','error':str(e)}
 def send_audio_by_id(self,m,media_id,as_voice_message=True):
  mid=str(media_id).strip()
  if not mid:return {'success':False,'status':'MEDIA_ID_MISSING','attempts':0}
  obj={'id':mid};obj.update({'voice':True} if as_voice_message else {})
  return self._send_with_retry({'messaging_product':'whatsapp','recipient_type':'individual','to':self._mobile(m),'type':'audio','audio':obj})
 def send_voice_bytes(self,m,audio_bytes,mime_type='audio/ogg',file_name='podx-reply.ogg'):
  start=time.perf_counter();up=self.upload_audio(audio_bytes,mime_type,file_name);ums=round((time.perf_counter()-start)*1000)
  if not up.get('success'):return {'success':False,'status':'VOICE_UPLOAD_FAILED','upload_result':up,'upload_ms':ums}
  s=time.perf_counter();res=self.send_audio_by_id(m,up['media_id'],True);return {**res,'media_id':up['media_id'],'upload_result':up,'upload_ms':ums,'message_send_ms':round((time.perf_counter()-s)*1000),'voice_send_total_ms':round((time.perf_counter()-start)*1000)}
 def download_media(self,media_id):
  if not self.is_configured():return {'success':False,'status':'NOT_CONFIGURED'}
  start=time.perf_counter()
  try:
   a=time.perf_counter();meta=self._http_client.get(f'https://graph.facebook.com/{self.api_version}/{str(media_id).strip()}',headers=self._auth_headers(),timeout=30);mms=round((time.perf_counter()-a)*1000)
   if not 200<=meta.status_code<300:return {'success':False,'status':'MEDIA_METADATA_HTTP_ERROR','http_status':meta.status_code,'provider_response':self._safe_json(meta),'metadata_ms':mms}
   md=meta.json();url=str(md.get('url','')).strip()
   if not url:return {'success':False,'status':'MEDIA_URL_MISSING','provider_response':md}
   a=time.perf_counter();r=self._http_client.get(url,headers=self._auth_headers(),timeout=60);dms=round((time.perf_counter()-a)*1000)
   if not 200<=r.status_code<300:return {'success':False,'status':'MEDIA_DOWNLOAD_HTTP_ERROR','http_status':r.status_code}
   return {'success':True,'status':'DOWNLOADED','content':r.content,'mime_type':md.get('mime_type') or r.headers.get('content-type'),'file_size':len(r.content),'metadata_ms':mms,'download_ms':dms,'media_total_ms':round((time.perf_counter()-start)*1000)}
  except httpx.TimeoutException:return {'success':False,'status':'MEDIA_TIMEOUT'}
  except (httpx.HTTPError,ValueError) as e:return {'success':False,'status':'MEDIA_NETWORK_ERROR','error':str(e)}
 def _send_once(self,url,headers,payload):
  try:
   r=self._http_client.post(url,headers=headers,json=payload,timeout=30);body=self._safe_json(r);ok=200<=r.status_code<300
   return {'success':ok,'status':'SENT_TO_PROVIDER' if ok else 'PROVIDER_HTTP_ERROR','http_status':r.status_code,'provider_response':body,'provider_message_id':self._message_id(body),'retryable':r.status_code in self.RETRYABLE_HTTP_STATUS}
  except httpx.TimeoutException:return {'success':False,'status':'TIMEOUT','retryable':True}
  except httpx.HTTPError as e:return {'success':False,'status':'NETWORK_ERROR','error':str(e),'retryable':True}
 @staticmethod
 def _safe_json(r):
  try:v=r.json();return v if isinstance(v,dict) else {'value':v}
  except ValueError:return {'raw_response':r.text}
 @staticmethod
 def _message_id(body):
  messages=body.get('messages',[]);return messages[0].get('id') if messages and isinstance(messages[0],dict) else None
