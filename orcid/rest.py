import requests
import datetime

from .constants import ORCID_PUBLIC_BASE_URL
from .utils import dictmapper, MappingRule as to

from .exceptions import NotFoundException

BASE_HEADERS = {'Accept':'application/orcid+json'}

BIO_PATH = ['orcid-profile','orcid-bio']
PERSONAL_DETAILS_PATH = BIO_PATH + ['personal-details']

def _parse_keywords(d):
    # XXX yes, splitting on commas is bad- but a bug in ORCID
    # (https://github.com/ORCID/ORCID-Parent/issues/27) makes this the  best
    # way. will fix when they do
    if d is not None:
        return [k.strip() for k in d.get('keyword',[{}])[0].get('value','').split(',')]
    return []

WebsiteBase = dictmapper('WebsiteBase', {
    'name':['url-name','value'],
    'url':['url', 'value']
})

class Website(WebsiteBase):
    def __unicode__(self):
        return self.url

    def __repr__(self):
        return "<%s %s [%s]>" % (type(self).__name__, self.name, self.url)

def _parse_researcher_urls(l):
    if l is not None:
        return [Website(d) for d in l]
    return []

def _parse_value(meta):
    if meta is not None:
        meta.get('value').strip().strip('\n')
    return

CitationBase = dictmapper('CitationBase', {
    'text':['citation'],
    'type':['work-citation-type']
})

class Citation(CitationBase):
    def __unicode__(self):
        return self.text

    def __repr__(self):
        return '<%s [type: %s]>' % (type(self).__name__, self.type)

ExternalIDBase = dictmapper('ExternalIDBase', {
    'id':['work-external-identifier-id','value'],
    'type':['work-external-identifier-type']
})

class ExternalID(ExternalIDBase):
    def __unicode__(self):
        return unicode(self.id)

    def __repr__(self):
        return '<%s %s:%s>' % (type(self).__name__, self.type, str(self.id))

PublicationBase = dictmapper('PublicationBase',{
    'title':['work-title','title','value'],
    'subtitle':['work-title','subtitle','value'],
    'url':['url','value'],
    'citation':to(['citation'], lambda d: Citation(d) if d is not None else None),
    'external_ids':to(['work-external-identifiers','work-external-identifier'],
                      lambda l: map(ExternalID, l) if l is not None else None),
})

class Publication(PublicationBase):
    def __repr__(self):
        return '<%s "%s">' % (type(self).__name__, self.title)

WORKS_PATH = ['orcid-profile', 'orcid-activities','orcid-works',]

def _parse_publications(l):
    if l is not None:
        return [Publication(d) for d in l]
    return []

Works = dictmapper('Works', {
    'publications':to(WORKS_PATH + ['orcid-work'], _parse_publications),
})

def _parse_dateparts_to_datetime(d):
    if d is not None:
        return datetime.date(int(d.get('year').get('value')), 
                             int(d.get('month', 1).get('value', 1)),
                             int(d.get('day', 1).get('value', 1))
                             )
    return None
                              

GrantBase = dictmapper('GrantBase', {
    'title': ['funding-title', 'title', 'value'],
    'funder': ['organization', 'name'],
    'value': to(['amount', 'value'], lambda v: int(v) if v is not None else None),
    'currency': ['amount', 'currency-code'],
    'start_date': to(['start-date'], _parse_dateparts_to_datetime),
    'end_date': to(['end-date'], _parse_dateparts_to_datetime)
    })
    
class Grant(GrantBase):
    def __repr__(self):
        return '<%s "%s">' % (type(self).__name__, self.title)

GRANTS_PATH = ['orcid-profile', 'orcid-activities', 'funding-list',]

def _parse_grants(l):
    if l is not None:
        return [Grant(d) for d in l]
    return []
    
Funding = dictmapper('Funding', {
    'grants':to(GRANTS_PATH + ['funding'], _parse_grants)
    })


AuthorBase = dictmapper('AuthorBase', {
    'orcid':['orcid-profile','orcid-identifier','path'],
    'family_name':PERSONAL_DETAILS_PATH + ['family-name','value'],
    'given_name':PERSONAL_DETAILS_PATH + ['given-names','value'],
    'biography':to(BIO_PATH + ['biography'], _parse_value),
    'keywords':to(BIO_PATH + ['keywords'], _parse_keywords),
    'identifiers_map': to(BIO_PATH + ['external-identifiers', 'external-identifier']),
    'researcher_urls':to(BIO_PATH + ['researcher-urls','researcher-url'],
                         _parse_researcher_urls),
})

class Author(AuthorBase):
    _loaded_works = None

    def _load_works(self):
        resp = requests.get(ORCID_PUBLIC_BASE_URL + self.orcid
                            + '/orcid-works', headers = BASE_HEADERS)
        self._loaded_works = Works(resp.json())

    @property
    def publications(self):
        if self._loaded_works is None:
            self._load_works()
        return self._loaded_works.publications


    def _load_funding(self):
        resp = requests.get(ORCID_PUBLIC_BASE_URL + self.orcid
                            + '/funding', headers = BASE_HEADERS)
        self._funding = Funding(resp.json())

    @property
    def grants(self):
        if not hasattr(self, '_funding'):
            self._load_funding()
        return self._funding.grants


    @property
    def identifiers(self):
        out = []
        for exid in self.identifiers_map or []:
            #import ipdb; ipdb.set_trace()
            d = {}
            d['id'] = exid["external-id-reference"]["value"]
            d['label'] = exid["external-id-common-name"]["value"]
            out.append(d)
        return out

    @property
    def websites(self):
        out = []
        for url in self.researcher_urls or []:
            d = {}
            d['url'] = url.url
            d['label'] = url.name
            out.append(d)
        return out

    def profile(self):
        return {
            'given_name': self.given_name,
            'family_name': self.family_name,
            'full_name': " ".join([n for n in [self.given_name, self.family_name] if n is not None]),
            'bio': self.biography,
            'identifiers': self.identifiers,
            'websites': self.websites,
            'keywords': self.keywords
        }

    def __repr__(self):
        return "<%s %s %s, ORCID %s>" % (type(self).__name__, self.given_name,
                                         self.family_name, self.orcid)

Citation = dictmapper('Citation', {
    'citation':['citation'],
    'citation_type':['work-citation-type']
})

def get(orcid_id):
    """
    Get an author based on an ORCID identifier.
    """
    url = "{}{}/orcid-profile".format(ORCID_PUBLIC_BASE_URL, unicode(orcid_id))
    resp = requests.get(url, headers=BASE_HEADERS)
    json_body = resp.json()
    return Author(json_body)

def search(query):
    resp = requests.get(ORCID_PUBLIC_BASE_URL + 'search/orcid-bio',
                        params={'q':unicode(query)}, headers=BASE_HEADERS)
    json_body = resp.json()
    return (Author(res) for res in json_body.get('orcid-search-results', {})\
            .get('orcid-search-result'))
