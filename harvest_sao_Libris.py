#the scripts harvests set=sao from Libris and stores the output in the path provided in OUTPUT_FILE
import time
import requests
from lxml import etree

OAI_URL = "https://libris.kb.se/api/oaipmh/"   # trailing slash, same as in the browser
PARAMS = {"verb": "ListRecords", "metadataPrefix": "marcxml", "set": "sao"}
OUTPUT_FILE = r"c:\script\sao.xml"
MAX_RETRIES = 5

NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}
MARC_NS = "http://www.loc.gov/MARC21/slim"

session = requests.Session()
session.headers["User-Agent"] = "sao-harvester/1.0"


def get_with_retry(params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(OAI_URL, params=params, timeout=120)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            status = getattr(e.response, "status_code", None)
            retryable = status in (None, 429, 500, 502, 503, 504)
            if retryable and attempt < MAX_RETRIES:
                wait = 2 ** attempt
                print(f"  error ({status or e}), retrying in {wait}s ({attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise


def harvest():
    count = 0
    token = None

    with open(OUTPUT_FILE, "wb") as out:
        out.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        out.write(f'<collection xmlns="{MARC_NS}">\n'.encode())

        while True:
            params = {"verb": "ListRecords", "resumptionToken": token} if token else PARAMS
            print(f"Fetching batch... {count} records so far")
            r = get_with_retry(params)

            try:
                root = etree.fromstring(r.content)
            except etree.XMLSyntaxError:
                print("Response was not valid XML:\n", r.text[:1000])
                raise

            err = root.find("oai:error", NS)
            if err is not None:
                if err.get("code") == "noRecordsMatch":
                    break
                raise RuntimeError(f"OAI error {err.get('code')}: {err.text}\nURL: {r.url}")

            for rec in root.iterfind(".//oai:record", NS):
                header = rec.find("oai:header", NS)
                if header is not None and header.get("status") == "deleted":
                    continue
                # namespace-agnostic: grab the <record> inside <metadata>
                marc = rec.xpath("oai:metadata//*[local-name()='record']", namespaces=NS)
                if marc:
                    out.write(etree.tostring(marc[0], encoding="utf-8", with_tail=False))
                    out.write(b"\n")
                    count += 1

            token_el = root.find(".//oai:resumptionToken", NS)
            if token_el is not None and token_el.text and token_el.text.strip():
                token = token_el.text.strip()
                time.sleep(0.5)
            else:
                break

        out.write(b"</collection>\n")

    print(f"Finished. {count} records saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    harvest()