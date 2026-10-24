#!/usr/bin/env python3
"""Local PDF mechanics. The active agent supplies reviewed translation blocks."""
import argparse
from collections import Counter
import hashlib
import html
import io
import json
import math
from pathlib import Path
import re
import sys
import unicodedata

def dependencies():
    try:
        import fitz
        import reportlab
    except ImportError as exc:
        local=Path(__file__).resolve().parents[1]/'.deps'
        if local.is_dir():
            sys.path.insert(0,str(local))
            try:
                import fitz
                import reportlab
                return fitz
            except ImportError:pass
        raise SystemExit('Missing PDF dependencies. Use the host bundled Python first; '
            'otherwise install requirements.txt in an isolated job environment. '+str(exc))
    return fitz

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def prepare(source):
    fitz=dependencies();source=Path(source).resolve();doc=fitz.open(source)
    if doc.needs_pass:raise ValueError('Encrypted source requires an authorized password.')
    job={'schema_version':1,'source':str(source),'sha256':digest(source),'pages':[],
         'blocks':[],'glossary':{},'config':{},'notes':[]}
    for i,page in enumerate(doc,1):
        if page.rotation:raise ValueError('Rotated pages need coordinate normalization before this renderer.')
        job['pages'].append(dict(number=i,width=page.rect.width,height=page.rect.height,
            reviewed=False,needs_ocr=not bool(page.get_text().strip())))
        for b in page.get_text('dict')['blocks']:
            if b['type']!=0:continue
            text='\n'.join(''.join(s['text'] for s in line['spans']) for line in b['lines'])
            job['blocks'].append(dict(id=f'B{len(job["blocks"])+1:05d}',page=i,
                bbox=list(b['bbox']),original=text,type='unclassified',action='unreviewed',
                source_style={'font_sizes':sorted({round(s['size'],2) for line in b['lines'] for s in line['spans']}),
                    'colors':sorted({f'#{s["color"]:06x}' for line in b['lines'] for s in line['spans']})}))
    return job

def chars(page):
    for b in page.get_text('rawdict')['blocks']:
        for line in b.get('lines',[]):
            for span in line['spans']:
                for char in span['chars']:
                    if not char['c'].isspace():yield char

def intersects(a,b):
    return min(a[2],b[2])>max(a[0],b[0])+0.01 and min(a[3],b[3])>max(a[1],b[1])+0.01

def inside(box,x,y):return box[0]-.2<=x<=box[2]+.2 and box[1]-.2<=y<=box[3]+.2

def numeric_tokens(text):
    return Counter(re.findall(r'\d+(?:\.\d+)?',unicodedata.normalize('NFKC',text).replace('−','-')))

def validate(job):
    fitz=dependencies();doc=fitz.open(job['source'])
    if digest(job['source'])!=job['sha256']:raise ValueError('Source SHA256 changed; prepare a new job.')
    if len(job['pages'])!=len(doc):raise ValueError('Page inventory does not match source.')
    if len({b['id'] for b in job['blocks']})!=len(job['blocks']):raise ValueError('Duplicate block IDs.')
    warnings=[]
    for i,page in enumerate(doc,1):
        info=job['pages'][i-1]
        if info.get('number')!=i or not info.get('reviewed'):raise ValueError(f'Page {i} is not reviewed.')
        if info.get('needs_ocr'):raise ValueError(f'Page {i} needs OCR; retain source visual and review OCR separately.')
        if abs(info['width']-page.rect.width)>.01 or abs(info['height']-page.rect.height)>.01:
            raise ValueError(f'Page {i} dimensions changed.')
        blocks=[b for b in job['blocks'] if b['page']==i]
        for b in blocks:
            box=b['bbox']
            if len(box)!=4 or not(0<=box[0]<box[2]<=page.rect.width+.01 and 0<=box[1]<box[3]<=page.rect.height+.01):
                raise ValueError(f'Invalid bbox: {b["id"]}')
            if b.get('action') not in ('translate','preserve'):raise ValueError(f'Unreviewed block: {b["id"]}')
            if b['action']=='translate':
                if b.get('type') in ('figure','table','equation','references'):
                    raise ValueError(f'Protected content marked for translation: {b["id"]}')
                if not b.get('translation','').strip():raise ValueError(f'Missing translation: {b["id"]}')
                before=numeric_tokens(b.get('original',''));after=numeric_tokens(b['translation'])
                if before!=after:
                    note=dict(block=b['id'],numeric_removed=list((before-after).elements()),
                              numeric_added=list((after-before).elements()))
                    if not b.get('numeric_review'):
                        raise ValueError('Unreviewed numeric change: '+json.dumps(note,ensure_ascii=False))
                    note['review']=b['numeric_review'];warnings.append(note)
            elif not b.get('reason'):raise ValueError(f'Preserved block lacks a reason: {b["id"]}')
        translated=[b for b in blocks if b['action']=='translate']
        for b in translated:
            for other in blocks:
                if other['id']!=b['id'] and intersects(b['bbox'],other['bbox']):
                    raise ValueError(f'Overlapping blocks: {b["id"]} / {other["id"]}')
        missing=[]
        for char in chars(page):
            x0,y0,x1,y1=char['bbox']
            if not any(inside(b['bbox'],(x0+x1)/2,(y0+y1)/2) for b in blocks):missing.append(char['c'])
        if missing:raise ValueError(f'Unclassified source text on page {i}: '+''.join(missing)[:160])
    if any(not 1<=b['page']<=len(doc) for b in job['blocks']):raise ValueError('Block page is out of range.')
    return warnings

def fonts(config):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates=[]
    if config.get('font'):candidates.append((config['font'],int(config.get('font_index',0))))
    candidates += [('/System/Library/Fonts/Supplemental/Songti.ttc',6),
        ('/System/Library/Fonts/STHeiti Light.ttc',0),
        ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',0),
        ('/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',0),
        ('C:/Windows/Fonts/simsun.ttc',0)]
    for path,index in candidates:
        if not Path(path).is_file():continue
        try:
            regular=TTFont('PaperCN',path,subfontIndex=index);pdfmetrics.registerFont(regular)
            if ord('中') not in regular.face.charWidths:continue
            bold=TTFont('PaperCNBold',path,subfontIndex=(1 if path.endswith('Songti.ttc') else index))
            pdfmetrics.registerFont(bold)
            for fb in ('/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
                       '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','C:/Windows/Fonts/arial.ttf'):
                if Path(fb).is_file():
                    fallback=TTFont('PaperFallback',fb);pdfmetrics.registerFont(fallback)
                    break
            return regular
        except Exception:
            if config.get('font')==path:raise
    raise ValueError('No embeddable Chinese TrueType font found. Set config.font and optional font_index.')

def wrap_cn(text,font,size,width):
    from reportlab.pdfbase import pdfmetrics
    closing=set('，。；：！？）】》〉、,.!?;:)]%²');opening=set('（【《〈([');result=[]
    for para in text.split('\n'):
        tokens=re.findall(r'\[\d+\]|[A-Za-z0-9μÅηⅠⅡⅢⅣⅤ]+(?:[./@_:+%\-][A-Za-z0-9μÅηⅠⅡⅢⅣⅤ]+)*| +|.',para)
        line=[]
        for token in tokens:
            metric=(''.join(line)+token).replace('ₓ','x').replace('₂','2')
            if line and pdfmetrics.stringWidth(metric,font,size)>width-1:
                carry=[]
                if token[0] in closing:
                    while line and line[-1].isspace():line.pop()
                    if line:carry.insert(0,line.pop())
                while line and (line[-1].isspace() or line[-1][-1] in opening):carry.insert(0,line.pop())
                if line:result.append(''.join(line).rstrip())
                line=carry
            if not line and token.isspace():continue
            line.append(token)
        result.append(''.join(line).rstrip())
    return '\n'.join(result)

def markup(text):
    from reportlab.pdfbase import pdfmetrics
    text=html.escape(text).replace('ηRad','η<sub>Rad</sub>')
    text=text.replace('MoOₓ','MoO<sub>x</sub>').replace('O₂','O<sub>2</sub>')
    # Markup tags are ASCII; apply fallback only to uncovered non-ASCII characters.
    primary=pdfmetrics.getFont('PaperCN').face.charWidths
    if 'PaperFallback' in pdfmetrics.getRegisteredFontNames():
        text=''.join(f'<font name="PaperFallback">{ch}</font>' if ord(ch)>127 and ord(ch) not in primary else ch for ch in text)
    return text.replace('\n','<br/>')

def overlay(page,blocks,config):
    from reportlab.pdfgen import canvas
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    regular=fonts(config);buffer=io.BytesIO();c=canvas.Canvas(buffer,pagesize=(page.rect.width,page.rect.height))
    audit=[]
    for block in blocks:
        text=block['translation'];kind=block['type'];x0,y0,x1,y1=block['bbox']
        glyph_text=text.replace('ₓ','x').replace('₂','2')
        from reportlab.pdfbase import pdfmetrics
        widths=set(regular.face.charWidths)
        if 'PaperFallback' in pdfmetrics.getRegisteredFontNames():widths.update(pdfmetrics.getFont('PaperFallback').face.charWidths)
        missing=sorted({ch for ch in glyph_text if not ch.isspace() and ord(ch) not in widths})
        if missing:raise ValueError(f'Missing font glyphs in {block["id"]}: {missing}')
        size=block.get('font_size',{'title':20,'heading':10.3,'caption':8,'footnote':7.65,
            'keywords':8.7,'abstract':9.5}.get(kind,9.65))
        floor=block.get('min_font_size',{'title':15,'footnote':7,'caption':7.5,'keywords':8}.get(kind,9))
        font='PaperCNBold' if kind in ('title','abstract') else 'PaperCN'
        while size>=floor-.001:
            leading=block.get('leading',size*{'title':1.32,'caption':1.19,'footnote':1.15,'heading':1.05}.get(kind,1.23))
            alignment=block.get('align','center' if kind in ('title','heading') else 'left')
            if alignment not in ('left','center','right','justify'):raise ValueError('Invalid alignment: '+block['id'])
            style=ParagraphStyle('CN',fontName=font,fontSize=size,leading=leading,wordWrap='CJK',
                alignment={'left':0,'center':1,'right':2,'justify':4}[alignment],
                textColor=block.get('color','#0045a6' if kind=='heading' else '#111111'))
            p=Paragraph(markup(wrap_cn(text,font,size,x1-x0)),style);w,h=p.wrap(x1-x0,y1-y0)
            if h<=y1-y0+.01:break
            size-=.15
        else:raise ValueError(f'Overflow at readable font floor: {block["id"]}. Revise geometry, not meaning.')
        p.drawOn(c,x0,page.rect.height-y0-h)
        audit.append(dict(id=block['id'],font_size=round(size,2),height=round(h,2),available_height=y1-y0))
    c.save();return buffer.getvalue(),audit

def panel_geometry(page,config):
    fitz=dependencies();margin=float(config.get('margin',10));gutter=float(config.get('gutter',16))
    top=float(config.get('top',24));bottom=float(config.get('bottom',8))
    if any(v<0 or not v.is_integer() for v in (margin,gutter,top,bottom)):
        raise ValueError('Panel margins must be nonnegative integer PDF points for pixel-aligned preservation.')
    w,h=page.rect.width,page.rect.height
    rx=math.ceil(margin+w+gutter)
    return (rx+w+margin,h+top+bottom,
        fitz.Rect(margin,top,margin+w,top+h),fitz.Rect(rx,top,rx+w,top+h))

def build(job,output):
    fitz=dependencies();warnings=validate(job);src=fitz.open(job['source']);clean=fitz.open(job['source'])
    config=job.get('config',{});out=fitz.open();layouts=[];omitted_links=[];overlays=[]
    for i,page in enumerate(src):
        blocks=[b for b in job['blocks'] if b['page']==i+1 and b['action']=='translate']
        # Fit first. A failed fit must not produce a partially translated deliverable.
        overlay_bytes,records=overlay(page,blocks,config)
        cn=clean[i]
        for block in blocks:cn.add_redact_annot(fitz.Rect(block['bbox']),fill=(1,1,1),cross_out=False)
        if blocks:cn.apply_redactions(images=0,graphics=0,text=0)
        overlays.append((overlay_bytes,records))
    # Freeze the complete cleaned document before grafting: a cached graft map
    # cannot safely import new object numbers created by later redactions.
    clean=fitz.open(stream=clean.tobytes(garbage=4,deflate=True),filetype='pdf')
    for i,page in enumerate(src):
        overlay_bytes,records=overlays[i]
        width,height,left,right=panel_geometry(page,config)
        spread=out.new_page(width=width,height=height)
        spread.show_pdf_page(left,src,i)
        spread.show_pdf_page(right,clean,i)
        odoc=fitz.open(stream=overlay_bytes,filetype='pdf');spread.show_pdf_page(right,odoc,0);odoc.close()
        spread.draw_line((left.x1+8,8),(left.x1+8,height-8),color=(.84,.85,.87),width=.5)
        spread.insert_text((left.x0+38,14),'ENGLISH',fontsize=7,color=(.35,.38,.42))
        spread.insert_text((right.x0+38,14),'CHINESE',fontsize=7,color=(.35,.38,.42))
        spread.insert_text((width-55,14),f'{i+1} / {len(src)}',fontsize=7,color=(.35,.38,.42))
        layouts.append(dict(page=i+1,left_rect=list(left),right_rect=list(right),blocks=records))
    # show_pdf_page imports vectors, not annotations. Resolve links explicitly after all pages exist.
    for i,page in enumerate(src):
        local=[b['bbox'] for b in job['blocks'] if b['page']==i+1 and b['action']=='translate']
        for side in ('left','right'):
            panel=fitz.Rect(layouts[i][side+'_rect'])
            for link in page.get_links():
                origin=list(link['from'])
                if side=='right' and any(intersects(origin,b) for b in local):
                    omitted_links.append(dict(page=i+1,reason='Chinese text reflow moves this hotspot'));continue
                new={'kind':link['kind'],'from':fitz.Rect(origin)+(panel.x0,panel.y0,panel.x0,panel.y0)}
                if link['kind']==fitz.LINK_URI:new['uri']=link['uri']
                elif link['kind'] in (fitz.LINK_GOTO,fitz.LINK_NAMED) and 0<=link.get('page',-1)<len(src):
                    dest=fitz.Rect(layouts[link['page']][side+'_rect']);point=link.get('to',fitz.Point(0,0))
                    if link['kind']==fitz.LINK_NAMED:
                        # Named destinations expose PDF bottom-left coordinates.
                        point=point*src[link['page']].transformation_matrix
                    if side=='right':
                        for target_block in job['blocks']:
                            if target_block['page']==link['page']+1 and target_block['action']=='translate' and inside(target_block['bbox'],point.x,point.y):
                                point=fitz.Point(target_block['bbox'][0],target_block['bbox'][1]);break
                    new.update(kind=fitz.LINK_GOTO,page=link['page'],to=fitz.Point(point.x+dest.x0,point.y+dest.y0),zoom=link.get('zoom',0))
                else:
                    omitted_links.append(dict(page=i+1,reason='Unsupported or unresolved original link',side=side));continue
                out[i].insert_link(new)
    toc=src.get_toc();out.set_toc(toc or [[1,f'Page {i+1}',i+1] for i in range(len(src))])
    meta={k:v for k,v in src.metadata.items() if k in ('title','author','subject','keywords','creator','producer') and v}
    meta['title']=job.get('title',meta.get('title',''))+' | English-Chinese bilingual'
    out.set_metadata(meta)
    output=Path(output).resolve()
    if output==Path(job['source']).resolve():raise ValueError('Output must not overwrite source.')
    output.parent.mkdir(parents=True,exist_ok=True)
    # Garbage collection prevents removed text from surviving in orphaned objects.
    out.save(output,garbage=4,deflate=True)
    record=dict(source_sha256=job['sha256'],output_sha256=digest(output),pages=layouts,
        warnings=warnings,omitted_links=omitted_links)
    output.with_suffix('.layout.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    return record

def pixdiff(a,b):
    from PIL import Image,ImageChops
    ia=Image.frombytes('RGB',(a.width,a.height),a.samples)
    ib=Image.frombytes('RGB',(b.width,b.height),b.samples)
    if ia.size!=ib.size:return -1
    return changed_pixels(ImageChops.difference(ia,ib))

def changed_pixels(image):
    from PIL import ImageChops
    r,g,b=image.split();mask=ImageChops.lighter(ImageChops.lighter(r,g),b)
    return image.width*image.height-mask.histogram()[0]

def audit(job,output,previews=None):
    fitz=dependencies();validate(job);src=fitz.open(job['source']);out=fitz.open(output)
    from PIL import Image,ImageDraw,ImageChops
    record={'passed':True,'pages':[],'limitations':[
        'Semantic translation quality and scientific symbol/unit correctness require source-grounded review.',
        'Chinese links inside reflowed text are omitted; original-side resolved links are retained.']}
    if len(src)!=len(out):raise ValueError('Output page count changed.')
    for i,page in enumerate(src):
        width,height,left,right=panel_geometry(page,job.get('config',{}))
        if abs(out[i].rect.width-width)>.01 or abs(out[i].rect.height-height)>.01:raise ValueError('Wrong spread geometry.')
        original=page.get_pixmap(alpha=False);lp=out[i].get_pixmap(clip=left,alpha=False)
        rp=out[i].get_pixmap(clip=right,alpha=False)
        ld=pixdiff(original,lp)
        a=Image.frombytes('RGB',(original.width,original.height),original.samples)
        b=Image.frombytes('RGB',(rp.width,rp.height),rp.samples)
        diff=ImageChops.difference(a,b);draw=ImageDraw.Draw(diff)
        translated=[x for x in job['blocks'] if x['page']==i+1 and x['action']=='translate']
        for block in translated:
            x0,y0,x1,y1=block['bbox'];draw.rectangle((int(x0)-2,int(y0)-2,int(x1)+2,int(y1)+2),fill=(0,0,0))
        rd=changed_pixels(diff)
        protected=[];preserved_text_mismatch=[]
        for block in job['blocks']:
            if block['page']!=i+1 or block['action']!='preserve':continue
            r=fitz.Rect(block['bbox']);r2=r+(right.x0,right.y0,right.x0,right.y0)
            expected=re.sub(r'\s+','',page.get_text(clip=r))
            actual=re.sub(r'\s+','',out[i].get_text(clip=r2))
            if expected!=actual:preserved_text_mismatch.append(block['id'])
            if block['type'] not in ('figure','table','equation','references'):continue
            # Crop full rasters at integer coordinates to avoid subpixel clip-origin differences.
            rect=tuple(map(int,r));n=changed_pixels(ImageChops.difference(a.crop(rect),b.crop(rect)))
            protected.append(dict(id=block['id'],changed_pixels=n))
        links=out[i].get_links()
        bad_links=sum(1 for link in links if link['kind']==fitz.LINK_GOTO and not 0<=link.get('page',-1)<len(out))
        expected_links=sum(1 for link in page.get_links() if link['kind']==fitz.LINK_URI or
            (link['kind'] in (fitz.LINK_GOTO,fitz.LINK_NAMED) and 0<=link.get('page',-1)<len(src)))
        left_links=sum(1 for link in links if left.contains(link['from']))
        expected_link_list=[link for link in page.get_links() if link['kind']==fitz.LINK_URI or
            (link['kind'] in (fitz.LINK_GOTO,fitz.LINK_NAMED) and 0<=link.get('page',-1)<len(src))]
        actual_link_list=[link for link in links if left.contains(link['from'])]
        link_target_mismatch=0
        for original_link,actual_link in zip(expected_link_list,actual_link_list):
            if original_link['kind']==fitz.LINK_URI:
                if actual_link.get('uri')!=original_link['uri']:link_target_mismatch+=1
            else:
                target_page=original_link['page'];target=original_link['to']
                if original_link['kind']==fitz.LINK_NAMED:target=target*src[target_page].transformation_matrix
                dest_left=panel_geometry(src[target_page],job.get('config',{}))[2]
                expected=fitz.Point(target.x+dest_left.x0,target.y+dest_left.y0)
                actual=actual_link.get('to',fitz.Point(-999,-999))
                if actual_link.get('page')!=target_page or abs(actual-expected)>.02:link_target_mismatch+=1
        # Search source word sequences in translated boxes to detect stale hidden source text.
        stale=[];missing_translation=[]
        for block in translated:
            r=fitz.Rect(block['bbox'])+(right.x0,right.y0,right.x0,right.y0)
            extracted=out[i].get_text(clip=r)
            latin=re.findall(r'[A-Za-z]{3,}(?:[ -]+[A-Za-z]{3,}){3,}',block.get('original',''))
            if any(s.lower() in extracted.lower() for s in latin):stale.append(block['id'])
            expected=''.join(re.findall(r'[\u3400-\u9fff]',block['translation']))
            actual=''.join(re.findall(r'[\u3400-\u9fff]',extracted))
            if expected and expected!=actual:missing_translation.append(block['id'])
        # Redaction reserializes text coordinates and can slightly change antialiasing.
        # Permit at most 0.01% outside pixels only when preserved text is identical;
        # original panel and figure/equation/reference pixels remain strict.
        outside_limit=max(0,int(original.width*original.height*.0001))
        ok=(ld==0 and rd<=outside_limit and not preserved_text_mismatch and not bad_links and
            left_links==expected_links and not link_target_mismatch and not stale and not missing_translation and all(x['changed_pixels']==0 for x in protected))
        record['pages'].append(dict(page=i+1,left_rect=list(left),right_rect=list(right),left_changed_pixels=ld,
            outside_translation_changed_pixels=rd,outside_pixel_limit=outside_limit,protected=protected,
            preserved_text_mismatch=preserved_text_mismatch,invalid_links=bad_links,
            original_left_links=expected_links,output_left_links=left_links,
            link_target_mismatch=link_target_mismatch,
            stale_english_blocks=stale,translation_text_mismatch=missing_translation,passed=ok))
        record['passed'] &= ok
        if previews:
            root=Path(previews);root.mkdir(parents=True,exist_ok=True)
            out[i].get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False).save(root/f'page-{i+1:03d}.png')
    return record

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('source');p.add_argument('manifest')
    for command in ('build','audit'):
        p=sub.add_parser(command);p.add_argument('manifest');p.add_argument('output')
        if command=='audit':p.add_argument('--previews')
    args=parser.parse_args()
    if args.command=='prepare':
        result=prepare(args.source);Path(args.manifest).parent.mkdir(parents=True,exist_ok=True)
        Path(args.manifest).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(args.manifest);return
    job=json.loads(Path(args.manifest).read_text())
    if args.command=='build':
        result=build(job,args.output);print(json.dumps({'output':str(Path(args.output).resolve()),'warnings':result['warnings'],
            'omitted_links':len(result['omitted_links'])},ensure_ascii=False))
    else:
        result=audit(job,args.output,args.previews)
        Path(args.output).with_suffix('.audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result,ensure_ascii=False));sys.exit(0 if result['passed'] else 2)

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError) as exc:raise SystemExit(str(exc))
