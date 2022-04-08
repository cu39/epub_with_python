from invoke import task
import os
from os import path
import shutil
from glob import glob
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
import zipfile as zf

IGNORE_FILES = (
    '.DS_Store',
    'Thumbs.db'
)
CONFIG_FILE = 'config.yml'
BUILD_DIR = 'temp'

def load_yaml():
    with open(CONFIG_FILE) as conf:
        config = yaml.safe_load(conf)
    return config

def shifted_path(path_str):
    return path_str[(path_str.find(path.sep) + 1):]

def file_paths(dir_path):
    if not path.isdir(dir_path):
        return []
    file_paths = glob(f'{dir_path}/*')
    return [shifted_path(file_path) for file_path in file_paths]

def image_paths():
    return file_paths(path.join('src', 'images'))

def font_paths():
    return file_paths(path.join('src', 'fonts'))

def jinja():
    def dot_to_hyphen(filename):
        return filename.replace('.', '-')

    context = load_yaml()
    context['images'] = [f for f in image_paths() if not f.endswith('cover.jpg')]
    context['fonts'] = font_paths()

    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape()
    )

    # テンプレート用ヘルパー関数を登録
    env.filters['shift_path'] = shifted_path
    env.filters['dot_to_hyphen'] = dot_to_hyphen

    # テンプレート読み込み
    tmpl = env.get_template('OEBPS/content.opf.j2')

    return tmpl.render(context)

@task
def build(c):
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
                    zip.write(entry.path, shifted_path(entry.path), zf.ZIP_DEFLATED, 9)

    config = load_yaml()

    if path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(path.join(BUILD_DIR, 'META-INF'))
    os.makedirs(path.join(BUILD_DIR, 'OEBPS'))

    # templates をスキャン
    # *.j2 のファイルはテンプレートとして temp へレンダリング
    # その他拡張子ならそのまま temp へコピー
    shutil.copy('templates/mimetype', BUILD_DIR)
    shutil.copy('templates/META-INF/container.xml', path.join(BUILD_DIR, 'META-INF'))
    with open(path.join(BUILD_DIR, 'OEBPS', 'content.opf'), 'w') as f:
        f.write(jinja())

    tree = list(os.walk('src'))

    directories = tree[0][1]
    for d in directories:
        shutil.copytree(path.join('src', d), path.join(BUILD_DIR, 'OEBPS', d))
    
    files = tree[0][2]
    for f in list(set(files).difference(IGNORE_FILES)):
        shutil.copy(path.join('src', f), path.join(BUILD_DIR, 'OEBPS', f))

    # src をスキャン
    # *.md のファイルは XHTML へ変換して temp へ書き出し
    # その他拡張子ならそのまま temp へコピー

    fn = config['epub_file_name']
    with zf.ZipFile(fn, 'w') as zip:
        zip.write(path.join(BUILD_DIR, 'mimetype'), 'mimetype', zf.ZIP_STORED, 0)

        meta_path = path.join(BUILD_DIR, 'META-INF')
        book_path = path.join(BUILD_DIR, 'OEBPS')
        for dn in (meta_path, book_path):
            write_files(zip, dn)
