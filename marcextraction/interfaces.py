"""the interface classes to allow for building a list of records and/or searching for relevant records
"""

from abc import ABCMeta, abstractclassmethod, abstractmethod, abstractproperty
from io import BytesIO
from lxml.etree import XMLParser, XML, tostring as XML_to_string
from os import scandir, stat
from os.path import exists, isfile, isdir
from pymarc import MARCReader
from pymarc.exceptions import RecordLengthInvalid
from pysolr import Solr
from requests import get
from requests.exceptions import ConnectionError
from urllib.parse import ParseResult, quote, unquote
from xml.etree import ElementTree

from .constants import LOOKUP
from .lookup import MarcFieldLookup
from .utils import create_ole_index_field, create_ole_query

class SolrIndexSearcher:
    """a class to be used to search a Solr index for a query
    """
    def __init__(self, index_url, index_type):
        """initializes an instance of the class SolrIndexSearcher 

        Args:
            index_url (str): the URL to the SOLR index that will be queried.
            index_type (str): a flag indicating which type of index is being used. 
                Needed for being able to generate the correct index field name
 
        """
        try: # have to check if index_url inputted is a resolveable URL
            get(index_url, "head")
            self.solr_index = Solr(index_url)
            self.index_url = self.solr_index.url
            self.field_creator = self._build_field_definer(index_type)
            self.query_creator = self._set_query_creator(index_type)
        except ConnectionError:
            pass # not sure what to do if ConnectionError does happen. 
                 # it's a deal breaker. should be logged somehow.

    def _build_field_definer(self, flag):
        """a private method to build the field definition

         Args
            flag (str): an indicate of what the field is in the index
        """
        if flag == 'ole':
            return create_ole_index_field
        else:
            raise ValueError("invalid index_type {}".format(flag))

    def _set_query_creator(self, flag):
        """a private method to set the query_creator function of the instance

        Args
            flag (str): an indicato of what kind of query construction needs to be done
        """
        if flag == 'ole':
            return create_ole_query
        else:
            raise ValueError("invalid index type '{}' for query creation".format(flag))

    def search(self, query_term, field=None, field_label=None, subfield=None, subfield_label=None):
        """a method to run a search on the index for a particular value in a particular field

        Args:
            query_term (str): the string to be searched. This string will be stemmed in Solr searches.
            query_field: the label for the MARC21 field that you want to search in.
            query_subfield: the label for the relevant subfield of the MARC21 field that you want to search.

        Returns:
            list. An iterable containing dictionaries for each matching record in the Solr index 
                for the query_term, query_field, and query_subfield.
        """
        if field and subfield:
            field = MarcFieldLookup(field=field, subfield=subfield)
        elif field_label and subfield_label:
            field = MarcFieldLookup(field_label=field_label, subfield_label=subfield_label)
        elif field:
            field = MarcFieldLookup(field=field)
        elif field_label:
            field = MarcFieldLookup(field_label=field_label)
        else:
            field = MarcFieldLookup()
        fields = field.show_index_fields()
        query_chain = []
        for field in fields:
            full_field = self.field_creator(field)
            query_string = self.query_creator(full_field, query_term)
            query_chain.append(query_string)

        if query_chain:
            result = self.solr_index.search(q=' '.join(query_chain), fl='controlfield_001', rows=1000)
        else:
            result = self.solr_index.search(query_term, fl='controlfield_001', rows=1000)
        if result.hits > 1000:
            raise Exception("you are performing a Solr search with more than 1000 hits. I can only get searches with 1000 at this time")
        else:
            records = [x.get("controlfield_001") for x in result.docs]
            return records

class OnDiskSearcher:
    """a class to use for building up a list of exported MARC files at a particular location on-disk

    Useage:
        searcher  = OnDiskSeacher(location='/path/to/marc/records')
        searcher.search('Cartographic Mathematical Data', 'Spatial coordinates')


    """
    def __init__(self, writeable_object=None, location=None):
        if location and exists(location):
            self.records = self._build_list_of_records(location)
            self.total = len(self.records)
        elif writeable_object:
            validity, records = self._check_if_real_marc_record(
                writeable_object.read())
            self.records = records if validity else []
            self.total = len(records) if validity else 0
        self.errors = []

    def _check_if_real_marc_record(self, some_bytes):
        """a method to check of a chunk of bytes is in fact a MARC record

        Returns a tuple, first element is True|False evaluating whether it was a MARC record and
        second element is either None or a list of MARC records as dictionaries if first element is True

        :param some_bytes: a chunk of binary data

        :rtype tuple
        """
        try:
            with BytesIO(some_bytes) as read_file:
                reader = MARCReader(read_file)
                return (True, [record for record in reader])
        except RecordLengthInvalid:
            msg = "not a valid MARC record"
            self.errors.append(msg)
            return (False, None)

    def count(self):
        """a method to return the total number of records extracted

        Returns:
            int. total records found on-disk
        """
        return self.total

    def _find_marc_files(self, path):
        """a generator function to return a list of valid MARC records found from a particular location on-disk

        Args:
            path (str): a location on disk to a file or a directory

        Returns:
            generator. an interable containing MARC record objects 
        """
        for n_thing in scandir(path):
            if n_thing.is_dir():
                yield from self._find_marc_files(n_thing.path)
            elif n_thing.is_file():
                bytes_file = open(n_thing.path, 'rb')
                bytes_data = bytes_file.read()
                bytes_file.close()
                validity, data_package = self._check_if_real_marc_record(
                    bytes_data)
                if validity:
                    yield data_package

    def _build_list_of_records(self, path_on_disk):
        """a  method to get a list of MARC records transformed to dictionaries to allow for searching

        Args:
            path_on_disk (str): a particular location on-disk

        Returns:
            list. an iterable containing dictionaries representing MARC records
        """
        records = []
        if isdir(path_on_disk):
            for n_package in self._find_marc_files(path_on_disk):
                records += [x.as_dict() for x in n_package]
        elif isfile(path_on_disk):
            bytes_file = open(path_on_disk, 'rb')
            bytes_data = bytes_file.close()
            bytes_file.close()
            validity, data_package = self._check_if_real_marc_record(
                bytes_data)
            if validity:
                records += [record.as_dict() for record in data_package]
        return records

    def search(self, query_term, field=None, field_label=None, subfield=None, subfield_label=None):
        """a method to search for records matching query term and field lookup

        Args:
            query term (str): a word or phrase that should be present in relevant MARC records

        KWArgs:
            field (str): a MARC field number to target your search to
            field_label (str): the official MARC21 label for a MARC field to target your search to
            subfield (str): the subfield code to target your search to
            subfield_label (str): the official MARC21 label for the subfield code to target your search to
        Returns:
            list. an iterable containing dicitonaries

        :rtype list
        """
        if field and subfield:
            field = MarcFieldLookup(field=field, subfield=subfield)
        elif field_label and subfield_label:
            print("hi from search ondisk for field_label and subfield_label")
            field = MarcFieldLookup(field_label=field_label, subfield_label=subfield_label)
        elif field:
            field = MarcFieldLookup(field=field)
        elif field_label:
            field = MarcFieldLookup(field_label=field_label)
        fields = field.show_index_fields()
        counter = 0
        output = []
        for record in self.records:
          counter += 1
          for field in fields:
              main_field = field[0:3]
              sub_field = field[-1]
              for a_field in record.get("fields"):
                  if a_field.get(main_field):
                    for subfield in a_field.get(main_field).get("subfields"):
                        if subfield.get(sub_field):
                            if query_term in subfield.get(sub_field):
                                output.append(record)
        return output

    @classmethod
    def from_flo(cls, flo):
        """a method to instantiate an instance of OnDiskExtractor from a file-like object

        Args:
            flo (File Object): a file-like object with read, write methods 

        Returns:
            OnDiskSearcher
        """
        return cls(writeable_object=flo)

class OLERecordFinder:
    """a class to use for finding a particular MARC record from the OLE API

    Useage:
        finder = OLERecordFinder("1003495521", "https://example.com/oledocstore")
        is_it_there, data = finder.get_record()
        if is_it_there:
            return data
    """
    def __init__(self, bibnumber, ole_domain, ole_scheme, ole_path):
        self.identifier = bibnumber
        self.records = self._find_record(ole_domain, ole_scheme, ole_path, bibnumber)

    def _find_record(self, ole_domain, ole_scheme, ole_path, bibnumber):
        query_param_value = quote("id={}".format(self.identifier))
        query_string = "version=1.2&operation=searchRetrieve&query={}&startRecord=1&maximumRecords=1".format(
            query_param_value)
        url_object = ParseResult(scheme=ole_scheme, netloc=ole_domain,
                                 path=ole_path, query=query_string, params="", fragment="")
        url = url_object.geturl()
        data = get(url)
        parser = XMLParser(remove_blank_text=True)
        if data.status_code == 200:
            # handy code for cleaning up newlines and spaces from XML output taken from
            # https://stackoverflow.com/questions/3310614/remove-whitespaces-in-xml-string

            xml_doc = ElementTree.fromstring(data.content)
            found_records = xml_doc.findall("{http://www.loc.gov/zing/srw/}records/{http://www.loc.gov/zing/srw/}record/{http://www.loc.gov/zing/srw/}recordData/record")
            found_records = [ElementTree.tostring(x) for x in found_records]
            found_records =  [XML_to_string(XML(x, parser=parser)) for x in found_records]
            return found_records
        else:
            return None

    def get_record(self):
        """a public method to get the matching record (if one was found for the inputted bibnumber)

        Returns:
            tuple. first element is boolean result 
        """
        if self.records:
            return (True, self.records)
        else:
            return (False, None)