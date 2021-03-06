
from os import remove, rmdir, getlogin, listdir, environ
from os.path import join
from pymarc import Record, Field
import unittest
from six import BytesIO
from tempfile import TemporaryFile, TemporaryDirectory
from urllib.parse import urlparse

from marcextraction.interfaces import SolrIndexSearcher, OnDiskSearcher, OLERecordFinder
from marcextraction.utils import create_ole_index_field, create_ole_query

# in order to run tests need to run locally from a computer on the uchicago library subnet to test against library OLE indexes
# in linux/unix issue the following command 
# SOLR_INDEX="[uchicago solr index]" OLE_INDEX="[uchicago sru api]"  pytest tests/

SOLR_INDEX = environ["SOLR_INDEX"] 
OLE_INDEX = environ["OLE_INDEX"]

class Tests(unittest.TestCase):
    def setUp(self):
        pass

    def testExtractFromWriteableObject(self):
        """
        tests whether the following happens
        a.) the extractory builds the right extractor
        b.) the built extractor is able to extract the data from a file like object
        c.) the right available methods gets returned for retrieving the data  
        """

        record = Record()
        record.add_field(Field(tag='245', indicators=['0', '1'],
                               subfields=[
            'a', 'Test book :',
            'b', 'a simple test object /',
            'c', 'John Doe'])
        )
        flo = BytesIO(record.as_marc())
        extracted_data = OnDiskSearcher(writeable_object=flo)
        self.assertEqual(extracted_data.count(), 1)

    def testExtractFromDirectoryLocation(self):
        tempdir = TemporaryDirectory()

        record1 = Record()
        record1.add_field(Field(tag='245', indicators=['0', '1'],
                                subfields=[
                                'a', 'Test book :',
                                'b', 'a simple test object /',
                                'c', 'John Doe'])
                          )

        record2 = Record()

        record2.add_field(Field(tag='245', indicators=['0', '1'],
                                subfields=[
                                'a', 'Another test book :',
                                'b', 'a second test object /',
                                'c', 'Jane Doe'])
                          )
        with open(join(tempdir.name, 'file1.mrc'), 'wb') as write_file:
            write_file.write(record1.as_marc())
            write_file.seek(0)
        with open(join(tempdir.name, 'file2.mrc'), 'wb') as write_file:
            write_file.write(record2.as_marc())
            write_file.seek(0)
        searcher = OnDiskSearcher(location=tempdir.name)
        self.assertEqual(searcher.count(), 2)

    def testCreatingSolrIndexSearcher(self):
        searcher = SolrIndexSearcher(
            SOLR_INDEX, "ole")
        self.assertEqual(searcher.index_url,
                         SOLR_INDEX)

    def testSearchingOnDiscRecords(self):
        tempdir = TemporaryDirectory()

        record1 = Record()
        record1.add_field(Field(tag='245', indicators=['0', '1'],
                                subfields=[
                                'a', 'Test book :',
                                'b', 'a simple test object /',
                                'c', 'John Doe'])
                          )

        record2 = Record()

        record2.add_field(Field(tag='245', indicators=['0', '1'],
                                subfields=[
                                'a', 'Another test book :',
                                'b', 'a second test object /',
                                'c', 'Jane Doe'])
                          )
        with open(join(tempdir.name, 'file1.mrc'), 'wb') as write_file:
            write_file.write(record1.as_marc())
            write_file.seek(0)
        with open(join(tempdir.name, 'file2.mrc'), 'wb') as write_file:
            write_file.write(record2.as_marc())
            write_file.seek(0)

        searcher = OnDiskSearcher(location=tempdir.name)

        result = searcher.search('Test book', '245', ['a'])
        tempdir.cleanup()
        self.assertEqual(len(result), 1)

    def testSearchingVuFindWithTargetedField(self):
        searcher = SolrIndexSearcher(
            SOLR_INDEX, 'ole')
        results = searcher.search('Banana', field='245', subfields=['a'])
        self.assertEqual(len(results), 188)

    def testSearchingVuFindWithPhraseSearch(self):
        searcher = SolrIndexSearcher(
            SOLR_INDEX, 'ole')
        results = searcher.search('Social scientist', field='245', subfields=['a'], phrase_search=True)
        self.assertEqual(len(results), 119)


    def testSearchingOleIndex(self):
        url_object = urlparse(OLE_INDEX)
        finder = OLERecordFinder("4270571", url_object.netloc, url_object.scheme, url_object.path)
        check = finder.get_record()
        self.assertEqual(check[0], True)
