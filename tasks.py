from invoke import task
import os
import zipfile as zf

IGNORE_FILES = (
    '.DS_Store',
    'Thumbs.db'
)

@task
def build(c):
    def strip_src(path):
        return path[(path.find('/') + 1):]

    def write_files(zip, dn):
        with os.scandir(dn) as d:
            for entry in d:
                if entry.is_dir():
                    print(f'Diving into {entry.path}')
                    write_files(zip, entry.path)
                else:
                    if entry.name in IGNORE_FILES:
                        continue
                    print(f'Writing {entry.path}')
                    zip.write(entry.path, strip_src(entry.path), zf.ZIP_DEFLATED, 9)

    fn = 'example.epub'
    with zf.ZipFile(fn, 'w') as zip:
        zip.write('src/mimetype', 'mimetype', zf.ZIP_STORED, 0)

        for dn in ('src/META-INF', 'src/OEBPS'):
            write_files(zip, dn)
