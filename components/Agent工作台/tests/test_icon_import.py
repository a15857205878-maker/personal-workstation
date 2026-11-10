from pathlib import Path
import sys,tempfile,unittest,hashlib
B=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(B/'个人工具中心新版/vendor'));sys.path.insert(0,str(B/'个人工具中心'))
from PIL import Image
from icon_import import import_icons

class ImportTests(unittest.TestCase):
    def test_png_is_imported_without_modifying_source_and_keeps_transparency(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.png';Image.new('RGBA',(32,16),(10,20,30,128)).save(source);before=source.read_bytes()
            result=import_icons([source],root/'added');self.assertEqual(result['added'],1);self.assertEqual(source.read_bytes(),before)
            dest=Path(result['paths'][0]);self.assertEqual(dest.suffix,'.ico')
            with Image.open(dest) as icon:
                rgba=icon.convert('RGBA');self.assertEqual(rgba.size,(32,32));self.assertEqual(rgba.getpixel((0,0))[3],0)
    def test_ico_copy_is_exact_and_repeat_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'icon.ico';Image.new('RGBA',(32,32),'red').save(source,format='ICO');raw=source.read_bytes()
            one=import_icons([source],root/'added');dest=Path(one['paths'][0]);self.assertEqual(dest.read_bytes(),raw)
            stamp=dest.stat().st_mtime_ns;two=import_icons([source],root/'added')
            self.assertEqual(two['existing'],1);self.assertEqual(dest.stat().st_mtime_ns,stamp)
    def test_bad_files_do_not_block_valid_items_or_change_existing_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bad=root/'bad.png';bad.write_text('not an image');good=root/'good.ico';Image.new('RGBA',(32,32),'blue').save(good,format='ICO')
            out=root/'added';out.mkdir();keep=out/'keep.txt';keep.write_text('keep')
            value=import_icons([bad,good],out);self.assertEqual(value['added'],1);self.assertEqual(len(value['errors']),1);self.assertEqual(keep.read_text(),'keep')
    def test_cancelled_selection_creates_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'added';self.assertEqual(import_icons([],out)['added'],0);self.assertFalse(out.exists())
if __name__=='__main__':unittest.main()
