"""
Tools to interact with the EIA API at https://www.eia.gov/opendata/
"""

import logging
import pandas as pd
from gridemissions import config
import requests
import re
import json
from os.path import dirname, join


BAs = [
    "AEC",
    "AECI",
    "AESO",
    "AVA",
    "AVRN",
    "AZPS",
    "BANC",
    "BCHA",
    "BPAT",
    "CEN",
    "CHPD",
    "CISO",
    "CPLE",
    "CPLW",
    "DEAA",
    "DOPD",
    "DUK",
    "EEI",
    "EPE",
    "ERCO",
    "FMPP",
    "FPC",
    "FPL",
    "GCPD",
    "GRIF",
    "GRID",
    "GRMA",
    "GVL",
    "GWA",
    "HGMA",
    "HQT",
    "HST",
    "IESO",
    "IID",
    "IPCO",
    "ISNE",
    "JEA",
    "LDWP",
    "LGEE",
    "MISO",
    "MHEB",
    "NBSO",
    "NEVP",
    "NSB",
    "NWMT",
    "NYIS",
    "OVEC",
    "PACE",
    "PACW",
    "PGE",
    "PJM",
    "PNM",
    "PSCO",
    "PSEI",
    "SC",
    "SCEG",
    "SCL",
    "SEC",
    "SEPA",
    "SOCO",
    "SPA",
    "SPC",
    "SRP",
    "SWPP",
    "TAL",
    "TEC",
    "TEPC",
    "TIDC",
    "TPWR",
    "TVA",
    "WACM",
    "WALC",
    "WAUW",
    "WWA",
    "YAD",
]

KEYS = {
    "E": {
        "D": "EBA.%s-ALL.D.H",
        "NG": "EBA.%s-ALL.NG.H",
        "TI": "EBA.%s-ALL.TI.H",
        "ID": "EBA.%s-%s.ID.H",
    },
    "CO2": {
        "D": "CO2_%s_D",
        "NG": "CO2_%s_NG",
        "TI": "CO2_%s_TI",
        "ID": "CO2_%s-%s_ID",
    },
    "SO2": {
        "D": "SO2_%s_D",
        "NG": "SO2_%s_NG",
        "TI": "SO2_%s_TI",
        "ID": "SO2_%s-%s_ID",
    },
    "NOX": {
        "D": "NOX_%s_D",
        "NG": "NOX_%s_NG",
        "TI": "NOX_%s_TI",
        "ID": "NOX_%s-%s_ID",
    },
    "CO2i": {"D": "CO2i_%s_D", "NG": "CO2i_%s_NG"},
    "SO2i": {"D": "SO2i_%s_D", "NG": "SO2i_%s_NG"},
    "NOXi": {"D": "NOXi_%s_D", "NG": "NOXi_%s_NG"},
}

SRC = ["COL", "NG", "NUC", "OIL", "OTH", "SUN", "UNK", "WAT", "WND", "GEO", "BIO"]

for src in SRC:
    KEYS["E"]["SRC_%s" % src] = "EBA.%s-ALL.NG." + src + ".H"

EIA_ALLOWED_SERIES_ID = []
for ba in BAs:
    EIA_ALLOWED_SERIES_ID += [KEYS["E"]["D"] % ba]
    EIA_ALLOWED_SERIES_ID += [KEYS["E"]["NG"] % ba]
    EIA_ALLOWED_SERIES_ID += [KEYS["E"]["TI"] % ba]
    for src in SRC:
        EIA_ALLOWED_SERIES_ID += [KEYS["E"][f"SRC_{src}"] % ba]
    for ba2 in BAs:
        EIA_ALLOWED_SERIES_ID += [KEYS["E"]["ID"] % (ba, ba2)]


class EIA_Scraper(object):
    """
    An interface with the EIA API.
    """

    def __init__(self):
        self.logger = logging.getLogger("root")

    def get(self, params):
        r = requests.get(self.BASE_URL + params)
        if r.status_code == 200:
            return json.loads(r.text)
        else:
            self.logger.warning("Request returned with code %d" % r.status_code)
        return {}


class EBA_field_searcher(EIA_Scraper):
    """
    A scraper to figure out what fields are in the API.
    Use this to check if things have changed.
    We expect to find:
    - 56 BAs for demand
    - 67 BAs for generation (including AVRN)
    - 67 BAs for total interchange (including AVRN)
    - 66 BAs for interchange exports (without AVRN)
    - 76 BAs for interchange imports (without AVRN, with 10 CAN/MEX areas)
    """

    def __init__(self):
        super().__init__()
        self.BASE_URL = "http://api.eia.gov/search/?search_term=series_id"
        self.SEARCH_KEYWORD = {
            "D": "-ALL.D.H",
            "NG": "-ALL.NG.H",
            "TI": "-ALL.TI.H",
            "ID": ".ID.H",
            "GAS": ".NG.GAS.H",
        }
        self.EXPECTED_HITS = {"D": 56, "NG": 67, "TI": 67, "ID": 315, "GAS": 0}
        self.series_id = {}  # For use by the outside world
        self._searchResults = {}  # For debugging
        self.bas = {}  # Which BAs do we have for each field?

    def build(self):
        for k in self.SEARCH_KEYWORD:
            if self.build_query(k) == -1:
                # Something went wrong - exit
                return -1

        for f in ["D", "NG", "TI"]:
            self.bas[f] = [re.split(r"\.|-|_", el)[1] for el in self.series_id[f]]
        self.bas["ID1"] = [re.split(r"\.|-|_", el)[1] for el in self.series_id["ID"]]
        self.bas["ID2"] = [re.split(r"\.|-|_", el)[2] for el in self.series_id["ID"]]

        # build generation source queries by hand as searching doesn't seem
        # to work...
        for src in SRC:
            self.series_id["NG.%s" % src] = [
                el.replace(".NG.", ".NG.%s." % src) for el in self.series_id["NG"]
            ]
        return 1

    def build_query(self, FIELD):
        nrows = 500
        field = self.SEARCH_KEYWORD[FIELD]
        r = self.get('&search_value="%s"&rows_per_page=%d' % (field, nrows))

        if "response" not in r:
            self.logger.error("No response field!")
            if "error" in r:
                self.logger.error(r["error"])
                return -1
            else:
                self.logger.error(r)
                raise KeyError("No response field")

        results = self._filter_search(r["response"]["docs"], FIELD)
        self._searchResults[FIELD] = results

        # Use this as a crude way to monitor changes in the API
        if len(results) != self.EXPECTED_HITS[FIELD]:
            self.logger.warning("Found %d results for %s" % (len(results), FIELD))

        self.series_id[FIELD] = [el["series_id"] for el in results]
        return r

    def _filter_search(self, res, FIELD):
        res = [el for el in res if ("(region)" not in el["name"][0])]
        res = [el for el in res if el["series_id"].startswith("EBA.")]
        return res


class EBA_data_scraper(EIA_Scraper):
    """
    A scraper to get EBA data.
    """

    def __init__(self):
        super().__init__()
        if "EIA_API_KEY" not in config:
            raise ValueError(
                "You need to provide an EIA_API_KEY in your config.json file"
            )
        self.BASE_URL = "http://api.eia.gov/series/?api_key=%s" % config["EIA_API_KEY"]

    def scrape(self, series_id, start="20191001T08Z", end=None, split_calls=False):
        """
        Returns a pd.DataFrame object.
        By default, don't separate out the calls - do this for the net
        generation by source columns where a lot of them are missing.
        """
        max_calls = 100

        if isinstance(series_id, str):
            series_id = [series_id]

        if split_calls:
            # Make each call individually
            return pd.concat(
                [
                    self.scrape(series_id=s, start=start, end=end, split_calls=False)
                    for s in series_id
                ],
                axis=1,
                sort=True,
            )

        if len(series_id) > max_calls:
            # We are limited to max_calls calls
            # -> Split the calls up into chunks
            chunks = [
                series_id[ii : ii + max_calls]
                for ii in range(0, len(series_id), max_calls)
            ]
            self.logger.warning("Splitting the calls up in %d chunks" % len(chunks))
            return pd.concat(
                [self.scrape(series_id=s, start=start, end=end) for s in chunks],
                axis=1,
                sort=True,
            )

        # Normal processing
        if end is None:
            query = "&series_id=%s&start=%s" % (";".join(series_id), start)
        else:
            query = "&series_id=%s&start=%s&end=%s" % (";".join(series_id), start, end)
        r = self.get(query)

        if "series" in r.keys():
            # Warning: there could be some missing entries in both columns and
            # rows
            # Missing rows: if columns were not all updated at the same time
            # Missing columns: if some queried columns don't exist
            if len(r["series"]) == 0:
                return pd.DataFrame()
            else:
                try:
                    return pd.concat(
                        [self._parse_series(s) for s in r["series"]], axis=1, sort=True
                    )
                except ValueError:
                    self.logger(r)
                    raise
        elif ("data" in r.keys()) and ("error" in r["data"].keys()):
            # If there were no valid results returned
            self.logger.debug(series_id)
            self.logger.debug(r["data"]["error"])
            return pd.DataFrame()
        else:
            raise ValueError("Unexpected case")

    def _parse_series(self, s):
        # Return as pd.DataFrame with date column as index
        df = pd.DataFrame(s["data"], columns=["Date", s["series_id"]])
        return df.set_index("Date")


def load_eia_columns():
    with open(join(dirname(__file__), "eia_columns.csv"), "r") as fr:
        eia_columns = fr.readline().strip()
    return eia_columns.split(",")
