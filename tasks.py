from invoke import task
import os
from os import path
import shutil
from glob import glob
import yaml
import re
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import Markdown
import zipfile as zf

IGNORE_FILES = (
    '.DS_Store',
    'Thumbs.db'
)
CONFIG_FILE = 'config.yml'
TEMPLATE_PATH = 'templates'
BUILD_DIR = 'temp'
BOOK_DIR_NAME = 'OEBPS'
BOOK_PATH = path.join(BUILD_DIR, BOOK_DIR_NAME)
MD_EXTENSIONS = [
    'meta',
    'abbr',
    'footnotes',
    'def_list',
]

def load_yaml():
    """設定YAMLを読み込んで辞書を返す
    """
    with open(CONFIG_FILE) as conf:
        config = yaml.safe_load(conf)
    return config

def shifted_path(path_str):
    """PATH文字列の最初の要素を削除して返す

    >>> shifted_path('foo/bar/baz')
    'bar/baz'
    """
    return path_str[(path_str.find(path.sep) + 1):]

def file_paths(dir_path):
    if not path.isdir(dir_path):
        return []
    file_paths = glob(path.join(dir_path, '*'))
    return [shifted_path(file_path) for file_path in file_paths]

def image_paths():
    return file_paths(path.join('src', 'images'))

def font_paths():
    return file_paths(path.join('src', 'fonts'))

def make_context(version='main'):
    """テンプレートへ渡すコンテキスト辞書を作る
    """
    context = load_yaml()
    images_without_cover = [
        f for f in image_paths() if not f.endswith('cover.jpg')
    ]
    context['images'] = images_without_cover
    context['fonts'] = font_paths()
    context['contents'] = context['versions'][version]['contents']
    context['cover_image'] = context['versions'][version]['cover_image']
    return context

def swap_ext(ext_from, ext_to, path_str):
    """PATH文字列の拡張子を置換する

    >>> swap_ext('jpeg', 'jpg', 'test.jpeg')
    'test.jpg'
    >>> swap_ext('md', 'xhtml', 'foo/bar/baz.md')
    'foo/bar/baz.xhtml'
    """
    return re.sub(f'(^.*)\.{ext_from}$', fr'\1.{ext_to}', path_str)

def make_jinja_env(template_path):
    """Jinja2環境を作る
    """

    def md_ext_to_xhtml(path_str):
        return swap_ext('md', 'xhtml', path_str)

    def md_to_title(path_str):
        """Markdownソースから（力技で）タイトルを取得
        """
        with open('src/' + path_str, 'r') as mdf:
            md_src = mdf.read()
            ptn = re.compile(r'^title: *(.*)$')
            for ln in md_src.splitlines():
                match = ptn.match(ln)
                if match:
                    return match.group(1)
        return 'NO TITLE'

    def dot_to_hyphen(filename):
        """Jinja2用ヘルパー関数
        ドットをハイフンへ全置換
        """
        return filename.replace('.', '-')

    env = Environment(
        loader=FileSystemLoader(template_path),
        autoescape=select_autoescape()
    )

    # テンプレート用ヘルパー関数を登録
    env.filters['shift_path'] = shifted_path
    env.filters['md_ext_to_xhtml'] = md_ext_to_xhtml
    env.filters['md_to_title'] = md_to_title
    env.filters['dot_to_hyphen'] = dot_to_hyphen

    return env

def append_version_suffix(fn, ver_suffix):
    """ファイル名にバージョン文字列を追加する

    >>> append_version_suffix('example.epub', 'trial')
    'example-trial.epub'
    """
    base, ext = path.splitext(fn)
    return f'{base}-{ver_suffix}{ext}'

@task(optional=['version'])
def build(c, version='main'):
    def write_as_xhtml(md_path):
        """Markdownファイルを読み込んでHTMLに変換し作業ディレクトリに保存する
        """
        md_withoutext = path.splitext(shifted_path(md_path))[0]
        with open(md_path, 'r') as mdf:
            md_src = mdf.read()
            md_body = md.convert(md_src)
            md_title = md.Meta['title'][0]  # md.convert() の後にする必要あり
            md.reset()
            xhtml_context = {
                'markdown_body': md_body,
                'title': md_title,
            }
            xhtml_src = tmpl_xhtml.render(xhtml_context)
            xhtml_fn = path.join(BOOK_PATH, f'{md_withoutext}.xhtml')
        with open(xhtml_fn, 'w') as xhtmlf:
            xhtmlf.write(xhtml_src)

    def write_files(zip, dn):
        """ディレクトリを走査してZIPファイルに書き込む
        """
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

    # 作業ディレクトリを削除
    if path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)

    # 必要なディレクトリを作成
    os.makedirs(path.join(BUILD_DIR, 'META-INF'))
    os.makedirs(BOOK_PATH)

    # assets の固定ファイルをコピー
    shutil.copy(path.join('assets', 'mimetype'), BUILD_DIR)
    shutil.copy(path.join('assets', 'META-INF', 'container.xml'), path.join(BUILD_DIR, 'META-INF'))

    # 設定読み込み
    context = make_context(version)

    env = make_jinja_env(TEMPLATE_PATH)

    # OPFテンプレート読み込み
    tmpl_opf = env.get_template('content.opf.j2')
    # OPFテンプレートを作業ディレクトリへレンダリング
    with open(path.join(BOOK_PATH, 'content.opf'), 'w') as f:
        f.write(tmpl_opf.render(context))

    # 目次テンプレート読み込み
    tmpl_nav = env.get_template('nav.xhtml.j2')
    # 目次テンプレートを作業ディレクトリへレンダリング
    with open(path.join(BOOK_PATH, 'nav.xhtml'), 'w') as f:
        f.write(tmpl_nav.render(context))

    tree = list(os.walk('src'))

    # src 直下のディレクトリはそのままコピー
    directories = tree[0][1]
    for d in directories:
        shutil.copytree(path.join('src', d), path.join(BOOK_PATH, d))

    # Markdown オブジェクト作成
    md = Markdown(extensions=MD_EXTENSIONS)

    # XHTML 用テンプレート作成
    tmpl_xhtml = env.get_template('xhtml.j2')

    # src 直下のファイルリストから無視指定ファイルを除外
    all_files = tree[0][2]
    files = list(set(all_files).difference(IGNORE_FILES))

    # *.xhtml と *.css はそのままコピー
    for f in files:
        fn, ext = os.path.splitext(f)
        if ext in ('.xhtml', '.css'):
            shutil.copy(path.join('src', f), path.join(BOOK_PATH, f))

    # *.md は context.versions を参照して XHTML に変換
    for f in context['versions'][version]['contents']:
        src_path = path.join('src', f)
        assert os.path.isfile(src_path), f'\'{src_path}\'が存在しません。config.ymlとsrcディレクトリ内の対応を確認してください'
        fn, ext = os.path.splitext(f)
        if ext == '.xhtml':
            shutil.copy(src_path, path.join(BOOK_PATH, f))
        elif ext == '.md':
            write_as_xhtml(src_path)

    # 出力EPUBファイル名
    fn = context['epub_file_name']
    # バージョンがmainでない場合はバージョン文字列を足す
    if version != 'main':
        fn = append_version_suffix(fn, version)

    # EPUBファイル書き込み
    with zf.ZipFile(fn, 'w') as zip:
        zip.write(path.join(BUILD_DIR, 'mimetype'), 'mimetype', zf.ZIP_STORED, 0)

        meta_path = path.join(BUILD_DIR, 'META-INF')
        book_path = path.join(BOOK_PATH)
        for dn in (meta_path, book_path):
            write_files(zip, dn)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
