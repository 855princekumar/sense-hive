"""Every picture the docs show is in the repository (a renamed or forgotten
screenshot is a broken image on GitHub and PyPI), and every screenshot the
docs use is one tools/screenshots.py makes, so it can be taken again."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / 'README.md', ROOT / 'DOCKERHUB.md', *sorted((ROOT / 'docs').glob('*.md'))]
IMG = re.compile(r'(?:src="|\]\()([^")\s]+\.(?:png|svg|jpg|gif|webp))')


def images():
    for doc in DOCS:
        for ref in IMG.findall(doc.read_text(encoding='utf-8')):
            if not ref.startswith('http'):
                yield doc, ref


def test_every_image_in_the_docs_exists():
    missing = [f'{doc.name}: {ref}' for doc, ref in images() if not (doc.parent / ref).resolve().is_file()]
    assert not missing, missing


def test_every_screenshot_in_the_docs_is_taken_by_the_screenshot_tools():
    made = set(re.findall(r"shot\(\w+, '([\w-]+\.png)'\)", (ROOT / 'tools' / 'screenshots.py').read_text(encoding='utf-8')))
    made |= {'quickstart-laptop.png', 'quickstart-phone.png'}                # tools/live_e2e.py --shots
    used = {Path(ref).name for _, ref in images() if Path(ref).suffix == '.png' and 'assets/' in ref.replace('\\', '/')}
    assert used and used <= made, sorted(used - made)
