"""Offline maintenance tests; never download game assets in CI."""
import importlib.util
import io
import json
from http.client import IncompleteRead
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_card_composition', ROOT / 'tools/prepare_command_card_composition_assets.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


def source_png(size=(256, 256)):
    image = Image.new('RGBA', size)
    image.paste((210, 130, 20, 255), (20, 20, 100, 90))
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


class CompositionAssetToolTests(unittest.TestCase):
    def test_quantization_and_available_name_rows(self):
        data, rows, changed = assets.palette_png(source_png(), (256, 256))
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.mode, 'P')
            self.assertLessEqual(len(image.getcolors()), 256)
            self.assertEqual(image.size, (256, 256))
        self.assertEqual(rows, [0])
        self.assertEqual(changed, 0)

    def test_wrong_dimensions_and_invalid_image_are_rejected(self):
        with self.assertRaises(ValueError):
            assets.palette_png(source_png((128, 128)), (256, 256))
        with self.assertRaises(OSError):
            assets.palette_png(b'<html>not a png</html>', (256, 256))

    def test_cached_download_does_not_use_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / 'cached.png'
            data = source_png()
            cache.write_bytes(data)
            with patch.object(assets, 'urlopen', side_effect=AssertionError('network called')):
                self.assertEqual(assets.download('https://static.atlasacademy.io/test', cache), data)

    def test_404_is_recorded_as_missing_without_substitution(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / 'missing.png'
            error = HTTPError('https://static.atlasacademy.io/missing', 404, 'missing', None, None)
            with patch.object(assets, 'urlopen', side_effect=error) as request:
                self.assertIsNone(assets.download('https://static.atlasacademy.io/missing', cache))
                self.assertEqual(request.call_count, 1)
            self.assertFalse(cache.exists())

    def test_temporary_failure_is_not_treated_as_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(assets, 'urlopen', side_effect=TimeoutError('timeout')), patch.object(assets.time, 'sleep'):
                with self.assertRaises(TimeoutError):
                    assets.download('https://static.atlasacademy.io/test', Path(temporary) / 'missing.png')

    def test_partial_http_body_is_retried_without_caching(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / 'missing.png'
            with patch.object(assets, 'urlopen', side_effect=IncompleteRead(b'partial', 12)) as request, patch.object(assets.time, 'sleep'):
                with self.assertRaises(IncompleteRead):
                    assets.download('https://static.atlasacademy.io/test', cache)
                self.assertEqual(request.call_count, 3)
            self.assertFalse(cache.exists())

    def test_common_layer_inventory(self):
        self.assertEqual(len(assets.COMMON_NAMES), 12)
        self.assertEqual(len(set(assets.COMMON_NAMES)), 12)
        self.assertIn('card_bg_npbuster', assets.COMMON_NAMES)

    def test_cn_layer_deployment_and_incremental_preservation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'resource/base/image/CommandCards'
            root.mkdir(parents=True)
            (root/'manifest').write_text(json.dumps({'servants': {'100': []}}), encoding='utf8')
            jp, cn = root/'jp-source', root/'cn-source'
            for name in assets.COMMON_NAMES:
                part = 'bg_np' if name.startswith('card_bg_np') else name.split('_')[1]
                for folder in (jp,cn):
                    folder.mkdir(exist_ok=True)
                    (folder/(name+'.png')).write_bytes(source_png(assets.COMMON_SIZES[part]))
            def run(extra):
                argv = ['prepare', '--root', str(root), '--common-source', str(jp), '--write', *extra]
                with patch.object(sys, 'argv', argv), patch.object(assets, 'ROOT', root), patch.object(assets, 'urlopen', side_effect=AssertionError('network called')):
                    assets.main()
            run(['--cn-common-source',str(cn)])
            cn_root = Path(temporary)/'resource/cn/image/CommandCards'
            entry_path = cn_root/'_composition/shared/card_icon_quick.png'
            before = entry_path.read_bytes()
            manifest = json.loads((cn_root/'_composition/manifest').read_text('utf8'))
            self.assertEqual(manifest['region'],'CN')
            self.assertEqual(len(manifest['shared']),12)
            self.assertEqual(manifest['shared']['card_icon_quick']['size'],[185,133])
            run([])
            self.assertEqual(entry_path.read_bytes(),before)
            self.assertEqual(json.loads((cn_root/'_composition/manifest').read_text('utf8')),manifest)
            # Invalid replacement sources must not alter any deployed asset.
            image = Image.new('RGBA',(150,73),(1,2,3,255))
            image.save(cn/'card_txt_arts.png')
            snapshot = (root/'_composition/manifest').read_bytes()
            with self.assertRaisesRegex(ValueError, 'alpha has not been restored'):
                run(['--cn-common-source',str(cn)])
            self.assertEqual((root/'_composition/manifest').read_bytes(),snapshot)
            self.assertEqual(entry_path.read_bytes(),before)

    def test_deployment_failure_restores_overwritten_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage, dest, backup = root / 'staged', root / 'dest', root / 'backup'
            stage.mkdir()
            dest.mkdir()
            (stage / 'a').write_bytes(b'new')
            (stage / 'b').write_bytes(b'new file')
            (dest / 'a').write_bytes(b'original')
            original_write = assets._atomic_write
            calls = []
            def fail_second(target, data):
                calls.append(target)
                if len(calls) == 2:
                    raise OSError('simulated disk failure')
                original_write(target, data)
            with patch.object(assets, '_atomic_write', side_effect=fail_second):
                with self.assertRaises(OSError):
                    assets.deploy(stage, dest, backup)
            self.assertEqual((dest / 'a').read_bytes(), b'original')
            self.assertFalse((dest / 'b').exists())
            self.assertEqual((backup / 'overwritten/a').read_bytes(), b'original')

    def test_np_names_use_identical_paths_in_separate_packs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root/'resource/base/image/CommandCards'
            cn = root/'resource/cn/image/CommandCards'
            base.mkdir(parents=True)
            (base/'manifest').write_text(json.dumps({'servants':{'100':[]}}),encoding='utf8')
            common = root/'common'
            common.mkdir()
            for name in assets.COMMON_NAMES:
                part = 'bg_np' if name.startswith('card_bg_np') else name.split('_')[1]
                (common/(name+'.png')).write_bytes(source_png(assets.COMMON_SIZES[part]))
            local = root/'originals'
            for region in ('JP','CN'):
                path=local/region/'100/card_servant_np.png'
                path.parent.mkdir(parents=True)
                image=Image.open(io.BytesIO(source_png()))
                if region=='CN':image=image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                image.save(path)
            argv=['prepare','--root',str(base),'--common-source',str(common),'--local-np-source',str(local),'--region','JP','--region','CN','--write']
            with patch.object(sys,'argv',argv),patch.object(assets,'ROOT',root),patch.object(assets,'urlopen',side_effect=AssertionError('network called')):
                assets.main()
            relative='np/100/card_servant_np.png'
            for region,folder in [('JP',base),('CN',cn)]:
                manifest=json.loads((folder/'_composition/manifest').read_text('utf8'))
                self.assertEqual(manifest['region'],region)
                self.assertEqual(manifest['np_names']['100']['file'],relative)
                self.assertTrue((folder/'_composition'/relative).is_file())
            self.assertNotEqual((base/'_composition'/relative).read_bytes(),(cn/'_composition'/relative).read_bytes())

    def test_multi_pack_deployment_rolls_back_all_regions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            packs=[]
            for region in ('JP','CN'):
                stage,dest=root/region/'stage',root/region/'dest'
                stage.mkdir(parents=True)
                dest.mkdir()
                (stage/'image').write_bytes(b'new')
                (dest/'image').write_bytes(region.encode())
                packs.append((stage,dest,region))
            original=assets._atomic_write
            calls=[]
            def fail_second(target,data):
                calls.append(target)
                if len(calls)==2:raise OSError('second region failed')
                original(target,data)
            with patch.object(assets,'_atomic_write',side_effect=fail_second),self.assertRaises(OSError):
                assets.deploy_packs(packs,root/'backup')
            for _,dest,region in packs:
                self.assertEqual((dest/'image').read_bytes(),region.encode())


if __name__ == '__main__':
    unittest.main()
