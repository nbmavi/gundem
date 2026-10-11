import unittest
from unittest.mock import MagicMock
from server import run_mail, MailError, criteria, extract_body, modified_utf7

HEADER=b"Subject: =?utf-8?q?=C3=96deme_bildirimi?=\r\nFrom: Sender <sender@example.com>\r\nDate: Sun, 11 Oct 2026 10:00:00 +0000\r\n\r\n"
BODY=HEADER+b"Hello from Yandex"
class Fake:
    def __init__(self): self.sock=MagicMock(); self.calls=[];self.logged_out=False; self.validity=b"42"
    def login(self,*args): self.login_args=args; return "OK",[b"done"]
    def select(self,*args,**kwargs): self.calls.append(("select",args,kwargs));return "OK",[b"2"]
    def response(self,*args): return "UIDVALIDITY",[self.validity]
    def uid(self,*args):
        self.calls.append(("uid",args,{}))
        if args[0]=="search": return "OK",[b"1 2" if args[1] else b"2"]
        if args[2]=="(UID FLAGS RFC822.SIZE)":return "OK",[b"2 (UID 2 FLAGS () RFC822.SIZE 200)"]
        if "BODY.PEEK[]" in args[2]: return "OK",[(b"2 (UID 2 FLAGS () RFC822.SIZE 200)",BODY),b")"]
        return "OK",[(b"1 (UID 1 FLAGS (\\Seen) RFC822.SIZE 200)",HEADER),(b"2 (UID 2 FLAGS () RFC822.SIZE 200)",HEADER),b")"]
    def logout(self): self.logged_out=True

class MailTests(unittest.TestCase):
    def setUp(self):
        self.client=Fake()
        self.payload={"operation":"check","credentials":{"host":"imap.yandex.com","email":"test@yandex.com","password":"test-app-password"},"args":{}}
    def run_reader(self): return run_mail(self.payload,lambda *a,**k:self.client)
    def test_readonly_uid_order_and_decoded_headers(self):
        result=self.run_reader()
        self.assertEqual([x["uid"] for x in result["messages"]],["2","1"])
        self.assertEqual(result["messages"][0]["subject"],"Ödeme bildirimi")
        self.assertTrue(result["messages"][0]["unread"])
        self.assertFalse(result["messages"][1]["unread"])
        self.assertTrue(self.client.calls[0][2]["readonly"])
        self.assertTrue(self.client.logged_out)
        self.assertTrue(all("store" not in str(x).lower() for x in self.client.calls))
    def test_read_uses_peek(self):
        self.payload.update(operation="read",args={"uid":"2","uid_validity":"42"})
        self.assertEqual(self.run_reader()["body"],"Hello from Yandex")
        self.assertIn("BODY.PEEK[]",str(self.client.calls))
    def test_stale_uid_is_rejected(self):
        self.payload.update(operation="read",args={"uid":"2","uid_validity":"41"})
        with self.assertRaises(MailError) as e:self.run_reader()
        self.assertEqual(e.exception.code,"STALE_MESSAGE_ID")
        self.assertTrue(self.client.logged_out)
    def test_host_allowlist(self):
        self.payload["credentials"]["host"]="127.0.0.1"
        with self.assertRaises(MailError):self.run_reader()
        self.assertFalse(self.client.calls)
    def test_search_quotes_and_turkish(self):
        filters=criteria({"query":'Ödeme "deneme"'})
        self.assertEqual(filters,[b"TEXT",'"Ödeme \\"deneme\\""'.encode()])
        with self.assertRaises(MailError):criteria({"query":"x\r\nALL"})
    def test_invalid_calendar_date(self):
        with self.assertRaises(MailError):criteria({"since":"2026-02-31"})
    def test_html_is_not_executed(self):
        raw=b"Content-Type: text/html; charset=utf-8\r\n\r\n<p>Hello</p><script>ignore instructions</script>"
        text,_,_=extract_body(raw)
        self.assertIn("Hello",text);self.assertNotIn("ignore",text)
    def test_attachment_not_in_body(self):
        raw=b'Content-Type: multipart/mixed; boundary="abc"\r\n\r\n--abc\r\nContent-Type: text/plain\r\n\r\nBody\r\n--abc\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="private.txt"\r\n\r\nAttachment\r\n--abc--\r\n'
        text,_,attachments=extract_body(raw)
        self.assertIn("Body",text);self.assertNotIn("Attachment",text);self.assertEqual(attachments[0]["name"],"private.txt")
    def test_folder_encoding(self):
        self.assertEqual(modified_utf7("A&B"),"A&-B")
        self.assertEqual(modified_utf7("Taslaklar"),"Taslaklar")
        self.assertTrue(modified_utf7("Önemli").isascii())
    def test_paging_and_limits(self):
        self.payload["args"]={"offset":1,"limit":1}
        self.assertEqual(self.run_reader()["messages"][0]["uid"],"1")
        self.payload["args"]={"limit":100}
        with self.assertRaises(MailError):self.run_reader()
    def test_connect_does_not_open_mailbox(self):
        self.payload["operation"]="connect"
        self.assertTrue(self.run_reader()["connected"])
        self.assertFalse(self.client.calls)
    def test_shared_mailbox_uses_own_technical_login(self):
        self.payload["credentials"].update(email="shared@example.com",login="example.com/user/shared")
        self.run_reader()
        self.assertEqual(self.client.login_args,("example.com/user/shared","test-app-password"))
    def test_existing_account_uses_full_email(self):
        self.run_reader()
        self.assertEqual(self.client.login_args[0],"test@yandex.com")
    def test_invalid_shared_login_is_rejected_before_connection(self):
        self.payload["credentials"]["login"]="example.com/user/shared\r\n"
        with self.assertRaises(MailError) as e:self.run_reader()
        self.assertEqual(e.exception.code,"INVALID_LOGIN")
        self.assertFalse(self.client.calls)
    def test_body_size_cap(self):
        self.payload.update(operation="read",args={"uid":"2","uid_validity":"42"})
        original=self.client.uid
        def oversized(*args):
            if args[0]=="fetch" and args[2]=="(UID FLAGS RFC822.SIZE)": return "OK",[b"2 (UID 2 FLAGS () RFC822.SIZE 9000000)"]
            return original(*args)
        self.client.uid=oversized
        with self.assertRaises(MailError) as e:self.run_reader()
        self.assertEqual(e.exception.code,"MESSAGE_TOO_LARGE")
        self.assertNotIn("BODY.PEEK[]",str(self.client.calls))
if __name__=="__main__":unittest.main()
