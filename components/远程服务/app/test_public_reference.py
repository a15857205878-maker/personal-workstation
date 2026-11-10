import unittest,threading,time
from unittest.mock import patch
from public_reference import public_target,extract_reference
class PublicReferenceTests(unittest.TestCase):
 def test_local_credential_and_non_https_urls_never_resolve(self):
  for url in ['http://example.com','https://127.0.0.1','https://[::1]','https://user:pass@example.com','https://example.com:8765','file:///C:/secret']:
   with self.subTest(url=url),self.assertRaises(ValueError):public_target(url)
 def test_resolved_private_or_mixed_addresses_fail_closed(self):
  for addresses in [['127.0.0.1'],['8.8.8.8','192.168.1.1']]:
   with patch('socket.getaddrinfo',return_value=[(2,1,6,'',(ip,443)) for ip in addresses]),self.assertRaises(ValueError):public_target('https://example.test/page')
 def test_public_target_pins_address_and_strips_fragments(self):
  with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]):
   host,path,address=public_target('https://example.test/a?q=1#ignored');self.assertEqual((host,path,address),('example.test','/a?q=1','8.8.8.8'))
 def test_extracts_content_and_styles_without_script_content(self):
  value=extract_reference('<title>参考页</title><style>body{color:red}</style><h1>标题</h1><script>SECRET_SCRIPT</script><p>介绍</p>')
  self.assertIn('参考页',value);self.assertIn('color:red',value);self.assertIn('介绍',value);self.assertNotIn('SECRET_SCRIPT',value)
 def test_multicast_and_translated_private_addresses_are_not_public(self):
  for ip in ['224.0.0.1','ff02::1','64:ff9b::7f00:1','64:ff9b::a00:1']:
   with patch('socket.getaddrinfo',return_value=[(2,1,6,'',(ip,443))]),self.assertRaises(ValueError):public_target('https://example.test')
 def test_element_style_is_preserved(self):
  self.assertIn('background:blue',extract_reference('<main style="background:blue">Hello</main>'))
 def test_wall_deadline_interrupts_stalled_response_headers(self):
  from public_reference import read_reference
  closed=threading.Event()
  class Connection:
   sock=None
   def __init__(self,*args):pass
   def request(self,*args,**kwargs):pass
   def getresponse(self):
    if not closed.wait(1):raise RuntimeError('blocking socket was not closed')
    raise OSError('closed')
   def close(self):closed.set()
  with patch('public_reference.public_target',return_value=('example.test','/','8.8.8.8')),patch('public_reference.PinnedHTTPS',Connection):
   start=time.monotonic()
   with self.assertRaises((OSError,ValueError)):read_reference('https://example.test',threading.Event(),timeout=.1)
   self.assertLess(time.monotonic()-start,.8)
 def test_cancel_during_dns_does_not_hold_task_worker(self):
  from public_reference import public_target
  from adapters import Cancelled
  stop=threading.Event();release=threading.Event();timer=threading.Timer(.05,stop.set)
  def dns(*args,**kwargs):release.wait(1);return [(2,1,6,'',('8.8.8.8',443))]
  timer.start();start=time.monotonic()
  try:
   with patch('socket.getaddrinfo',dns),self.assertRaises(Cancelled):public_target('https://example.test',stop)
   self.assertLess(time.monotonic()-start,.5)
  finally:release.set();timer.join()
 def test_tls_context_keeps_verification_enabled_with_existing_public_roots(self):
  from public_reference import tls_context
  import ssl
  context=tls_context();self.assertTrue(context.check_hostname);self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
if __name__=='__main__':unittest.main()
