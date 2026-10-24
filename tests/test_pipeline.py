import importlib.util,json,sys,tempfile,unittest
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('paper_pdf',SKILL/'scripts/paper_pdf.py')

class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(cls.mod)
        cls.mod.dependencies()

    def test_rejects_changed_source_and_unreviewed_blocks(self):
        import fitz
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'source.pdf'
            doc=fitz.open();doc.new_page().insert_text((50,80),'Test text 12%');doc.save(src)
            job=self.mod.prepare(src)
            with self.assertRaises(ValueError):self.mod.validate(job)
            job['pages'][0]['reviewed']=True
            for block in job['blocks']:
                block.update(action='preserve',type='publisher',reason='Test fixture')
            self.mod.validate(job)
            job['sha256']='wrong'
            with self.assertRaises(ValueError):self.mod.validate(job)

    def test_clean_text_geometry_links_and_variable_page_sizes(self):
        import fitz
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'source.pdf';out=root/'bilingual.pdf'
            doc=fitz.open()
            for w,h in [(420.6,595.7),(612,792)]:
                p=doc.new_page(width=w,height=h)
                p.insert_text((45,75),'Old source phrase 12%')
                p.insert_text((45,130),'Protected equation x = 2')
                p.draw_rect(fitz.Rect(40,160,160,210),color=(0,0,1))
            doc[0].insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(45,120,190,140),'page':1,'to':fitz.Point(45,130)})
            doc.save(src);doc.close()
            job=self.mod.prepare(src)
            for page in job['pages']:page['reviewed']=True
            for block in job['blocks']:
                if 'Old source' in block['original']:
                    block.update(action='translate',type='heading',translation='新译文数值 12%',bbox=[44,60,240,90],align='left',color='#000000',font_size=11)
                else:block.update(action='preserve',type='equation',reason='User preserves equations')
            self.mod.build(job,out)
            report=self.mod.audit(job,out)
            self.assertTrue(report['passed'],report)
            result=fitz.open(out)
            self.assertNotEqual(result[0].rect,result[1].rect)
            for i,page in enumerate(result):
                box=fitz.Rect(*report['pages'][i]['right_rect'])
                text=page.get_text(clip=box)
                self.assertIn('新译文',text)
                self.assertNotIn('Old source phrase',text)
                self.assertIn('Protected equation x = 2',text)
                spans=[s for b in page.get_text('dict',clip=box)['blocks'] for l in b.get('lines',[]) for s in l['spans'] if '新译文' in s['text']]
                self.assertEqual(spans[0]['color'],0)
                self.assertAlmostEqual(spans[0]['bbox'][0],box.x0+44,places=1)
            self.assertTrue(any(x['kind']==fitz.LINK_GOTO for x in result[0].get_links()))

    def test_protected_collision_and_overflow_are_errors(self):
        import fitz
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source.pdf';doc=fitz.open();p=doc.new_page();p.insert_text((45,75),'Old text');doc.save(src)
            job=self.mod.prepare(src);job['pages'][0]['reviewed']=True
            block=job['blocks'][0];block.update(action='translate',type='body',translation='译文',bbox=[40,60,200,90])
            job['blocks'].append(dict(id='F001',page=1,bbox=[50,65,90,85],type='figure',action='preserve',reason='Graphic'))
            with self.assertRaises(ValueError):self.mod.validate(job)
            job['blocks'].pop();block.update(translation='极长内容'*1000,bbox=[40,60,200,90])
            with self.assertRaises(ValueError):self.mod.build(job,Path(d)/'overflow.pdf')

if __name__=='__main__':unittest.main()
