# coding=utf-8
import os.path
import re
from collections import defaultdict
from itertools import chain

from dateutil.parser import parse as dt_parse
from nltk import data
from tokenize_uk import tokenize_words

_german_tokenizer = data.load(
    os.path.join(os.path.dirname(__file__), "data/german.pickle")
)
dob_regex = re.compile(r"\*\s?\d{2}\s?\.\s?\d{2}\s?.\s?\d{4}")
_useful_regex = re.compile(r"\d{2}\.\d{2}\.\d{4}\n\n", flags=re.M)
parse_number_regex = re.compile(r"^(\d+)\)?(.*)")
gmbh_regex = re.compile(r"[\s-]g?mbh", flags=re.I)
hrb_regex = re.compile(r"\b((?:HR\s?[AB]|VR|GnR|PR)\s?\d+)", flags=re.I)


def simplify_city(city):
    return (
        city.replace(" ", "")
        .replace("-", "")
        .replace(" ", "")
        .replace(".", "")
        .replace("/", "")
        .replace("(", "")
        .replace(")", "")
        .replace(":", "")
        .lower()
        .strip()
    )


with open(os.path.join(os.path.dirname(__file__), "data/cities.txt"), "r") as fp:
    GERMAN_CITIES = list(map(simplify_city, fp))


class ParsingError(Exception):
    pass


class Flag(object):
    __slots__ = ["flag", "text"]
    kind = "flags"

    def __init__(self, flag, text):
        self.flag = flag
        self.text = text

    def to_dict(self):
        return {"flag": self.flag, "text": self.text}

    def __str__(self):
        return "[Flag: {} ({})]".format(self.flag, self.text)


class Label(object):
    __slots__ = ["label", "text"]
    kind = "labels"

    def __init__(self, label, text):
        self.label = label
        self.text = text

    def to_dict(self):
        return {"label": self.label, "text": self.text}

    def __str__(self):
        return "[Label/{}: {}]".format(self.label, self.text)


class Error(object):
    __slots__ = ["kls", "text"]
    kind = "errors"

    def __init__(self, kls, text):
        self.kls = kls
        self.text = text

    def to_dict(self):
        return {"kls": self.kls, "text": self.text}

    def __str__(self):
        return "[Error/{}: {}]".format(self.kls, self.text)


class FullPerson(object):
    kls = "Person"
    kind = "officers"
    translations = {
        "einzelvertretungsberechtigt": "sole representation",
        "mit der befugnis, im namen der gesellschaft mit sich im eigenen namen oder als vertreter eines dritten rechtsgeschäfte abzuschließen": "with the power to enter into legal transactions on behalf of the Company with itself or as a representative of a third party",
    }

    titles = [
        "doktoringenieur", 
        "diplomingenieur", 
        "doctor", 
        "professor", 
        "diplombetriebswirt", 
        "diplomkauffrau", 
        "diplomkfm", 
        "diplombetriebswirt", 
        "diplomingenieur", 
        "diplomingenieur (fh)", 
        "diplomingenieur(fh)", 
        "diplom-ingenieur", 
        "diplom-kauffrau", 
        "doktoringenieur", 
        "freifrau", 
        "freiherr", 
        "professor",
    ]

    @staticmethod
    def parse_dob(dob):
        m = dob_regex.search(dob.strip(" ;."))

        if m:
            return dt_parse(m.group(0).strip("* ;."), dayfirst=True).date()
        else:
            raise ValueError("Cannot parse DOB {} using regex".format(dob))

    @classmethod
    def parse_dob_and_city(cls, chunk1, chunk2):
        try:
            dob = cls.parse_dob(chunk2)
            city = chunk1.strip(" *;.")
        except ValueError:
            dob = cls.parse_dob(chunk1)
            city = chunk2.strip(" *;.")

        return city, dob

    def __init__(self, text, doc=None):
        self.text = text
        chunks = text.split(",")
        self.description = ""
        self.payload = {}

        try:
            dob_position = None
            for i, c in enumerate(chunks):
                if dob_regex.search(c.strip(" ;.")):
                    dob_position = i
                    break

            if dob_position is None:
                if gmbh_regex.search(self.text) or hrb_regex.search(self.text):
                    self.company_name = self.text
                    self.payload = {"company_name": self.company_name.strip()}
                else:
                    if len(chunks) == 2:
                        self.lastname = chunks[0].strip(" *;.")
                        self.name = chunks[1].strip(" *;.")
                        self.payload = {"name": self.name, "lastname": self.lastname}
                    elif len(chunks) == 3:
                        self.lastname = chunks[0].strip(" *;.")
                        self.name = chunks[1].strip(" *;.")
                        self.city = chunks[2].strip(" *;.")
                        self.payload = {
                            "name": self.name,
                            "lastname": self.lastname,
                            "city": self.city,
                        }
                    elif len(chunks) == 4:
                        self.lastname = chunks[0].strip(" *;.")
                        self.name = chunks[1].strip(" *;.")
                        self.position = chunks[2].strip(" *;.")
                        self.city = chunks[3].strip(" *;.")
                        self.payload = {
                            "name": self.name,
                            "lastname": self.lastname,
                            "position": self.position,
                            "city": self.city,
                        }
                    else:
                        raise ValueError(
                            "a person without DOB, number of chunks: {}".format(
                                len(chunks)
                            )
                        )
            elif len(chunks) == 4:
                self.lastname = chunks[0].strip(" *;.")
                self.name = chunks[1].strip(" *;.")
                self.city, self.dob = self.parse_dob_and_city(chunks[2], chunks[3])
                self.payload = {
                    "name": self.name,
                    "lastname": self.lastname,
                    "city": self.city,
                    "dob": self.dob,
                }
            elif len(chunks) == 5:
                self.lastname = chunks[0].strip(" *;.")
                self.name = chunks[1].strip(" *;.")
                if dob_position == 4:
                    self.position = chunks[2].strip(" *;.")
                    self.city, self.dob = self.parse_dob_and_city(chunks[3], chunks[4])
                    self.payload = {
                        "name": self.name,
                        "lastname": self.lastname,
                        "city": self.city,
                        "dob": self.dob,
                        "position": self.position,
                    }
                else:
                    self.city, self.dob = self.parse_dob_and_city(chunks[2], chunks[3])
                    self.flag = chunks[4].strip(" *;.")
                    if self.flag in self.translations:
                        self.flag = self.translations[self.flag]

                    self.payload = {
                        "name": self.name,
                        "lastname": self.lastname,
                        "city": self.city,
                        "dob": self.dob,
                        "flag": self.flag,
                    }
            elif len(chunks) == 6:
                self.lastname = chunks[0].strip(" *;.")
                self.name = chunks[1].strip(" *;.")
                self.city, self.dob = self.parse_dob_and_city(chunks[2], chunks[3])
                self.flag = (chunks[4] + chunks[5]).strip(" *;.")
                if self.flag.lower() in self.translations:
                    self.flag = self.translations[self.flag.lower()]

                self.payload = {
                    "name": self.name,
                    "lastname": self.lastname,
                    "city": self.city,
                    "dob": self.dob,
                    "flag": self.flag,
                }
            elif len(chunks) == 3:
                self.lastname = chunks[0].strip(" *;.")
                self.name = chunks[1].strip(" *;.")
                self.dob = self.parse_dob(chunks[-1])

                self.payload = {
                    "name": self.name,
                    "lastname": self.lastname,
                    "dob": self.dob,
                }
            else:
                raise ValueError(
                    "no valid patter found, number of chunks: {}".format(len(chunks))
                )

            if len(self.payload.get("name", "")) > 50 and not hasattr(self, "dob"):
                raise ValueError(
                    "Name is too long: {}".format(self.name)
                )

            if len(self.payload.get("lastname", "")) > 100 and not hasattr(self, "dob"):
                raise ValueError(
                    "Lastname is too long: {}".format(self.name)
                )

            if re.search(r"\d", self.payload.get("name", "")):
                raise ValueError(
                    "Digits in name: {}".format(self.name)
                )

        except ValueError as e:
            raise ParsingError(
                "Cannot parse a {} from {}, error text was {}".format(self.kls, text, e)
            )

    def to_dict(self):
        if "lastname" in self.payload:
            for field_name in ["lastname", "name"]:
                if "geborene" in self.payload[field_name]:
                    try:
                        self.payload[field_name], self.payload["maidenname"] = self.payload[
                            field_name
                        ].split(" geborene", 1)
                    except ValueError:
                        continue

                    self.payload["maidenname"] = (
                        self.payload["maidenname"].replace("geborene", "").strip()
                    )
                    self.payload[field_name] = self.payload[field_name].strip()
                    self.payload["maidenname"] = self.payload["maidenname"].strip()

            if ":" in self.payload["lastname"]:
                _, self.payload["lastname"] = self.payload["lastname"].split(":", 1)
                self.payload["lastname"] = self.payload["lastname"].strip()

            m = parse_number_regex.search(self.payload["lastname"])
            if m:
                self.payload["ref"] = int(m.group(1))
                self.payload["lastname"] = m.group(2).strip()

            for title in self.titles:
                if self.payload["lastname"].lower().startswith(title):
                    self.payload["prof_title"] = title
                    self.payload["lastname"] = re.sub(title, "", self.payload["lastname"], flags=re.I).strip()
                    break

        if "company_name" in self.payload:
            m = parse_number_regex.search(self.payload["company_name"])
            if m:
                self.payload["ref"] = int(m.group(1))
                self.payload["company_name"] = m.group(2).strip()

        if getattr(self, "dismissed", False):
            self.payload["dismissed"] = True

        return {"class": self.kls, "text": self.text, "payload": self.payload}

    def __str__(self):
        if self.description:
            return "[{}: {}] {}".format(self.kls, self.text, self.description)
        else:
            return "[{}: {}]".format(self.kls, self.text)


class ManagingDirector(FullPerson):
    kls = "ManagingDirector"


class DismissedManagingDirector(FullPerson):
    kls = "DismissedManagingDirector"
    dismissed = True


class RetiredManagingDirector(FullPerson):
    kls = "RetiredManagingDirector"
    dismissed = True


class RetiredPersonalPartner(FullPerson):
    kls = "RetiredPersonalPartner"
    dismissed = True


class RetiredBoard(FullPerson):
    kls = "RetiredBoard"
    dismissed = True


class Owner(FullPerson):
    kls = "Owner"


class NotLongerOwner(FullPerson):
    kls = "NotLongerOwner"
    dismissed = True


class SingleProcuration(FullPerson):
    kls = "SingleProcuration"


class Procuration(FullPerson):
    kls = "Procuration"


class NewProcuration(FullPerson):
    kls = "NewProcuration"


class PersonalPartner(FullPerson):
    kls = "PersonalPartner"


class Liquidator(FullPerson):
    kls = "Liquidator"


class NotALiquidator(FullPerson):
    kls = "NotALiquidator"
    dismissed = True


class BecameLiquidator(FullPerson):
    kls = "BecameLiquidator"


class ProcurationCancelled(FullPerson):
    kls = "ProcurationCancelled"
    dismissed = True


class CommonProcuration(FullPerson):
    kls = "CommonProcuration"


class NotAProcurator(FullPerson):
    kls = "NotAProcurator"
    dismissed = True


class RemovedFromBoard(FullPerson):
    kls = "RemovedFromBoard"
    dismissed = True


class AppointedBoard(FullPerson):
    kls = "AppointedBoard"


class AppointedManagingDirector(FullPerson):
    kls = "AppointedManagingDirector"


class AbstractNotice:
    predecessor_regex = re.compile(r"bisher\s?\:?\s?(?:AG|Amtsgericht)", flags=re.I)
    successor_regex = re.compile(
        r"(jetzt|nun|nunmehr)\s?\:?\(?\s?(?:AG|Amtsgericht)", flags=re.I
    )

    def identify_notice_type(self):
        if self.successor_regex.search(self.text):
            return "successor"

        if self.predecessor_regex.search(self.text):
            return "predecessor"

        return None

    def try_to_deduct_registration(self):
        if self.payload.get("court"):
            court_position = self.text.index(self.payload["court"])
            from_position = None
            to_position = None

            if "from" in self.payload:
                from_position = self.text.index(self.payload["from"])
                if from_position > court_position:
                    from_position = None

            if "to" in self.payload:
                to_position = self.text.index(self.payload["to"])
                if to_position > court_position:
                    to_position = None

            if from_position is not None:
                self.payload["registration_fuzzy"] = True
                if to_position is not None and to_position > from_position:
                    self.payload["registration"] = "successor"
                else:
                    self.payload["registration"] = "predecessor"
            elif to_position is not None:
                self.payload["registration_fuzzy"] = True
                self.payload["registration"] = "successor"

    def try_to_find_city(self, city):
        if not city:
            return None

        city_chunks = city.split(" ")
        for x in range(len(city_chunks)):
            option = " ".join(city_chunks[: len(city_chunks) - x])
            if simplify_city(option) in GERMAN_CITIES:
                return option.strip(" ,.():")

        return city_chunks[0].strip(" ,.():")

    def to_dict(self):
        self.payload["used_regex"] = ", ".join(self.payload["used_regex"])

        if "from" in self.payload:
            self.payload["from"] = self.try_to_find_city(self.payload["from"])

        if "to" in self.payload:
            self.payload["to"] = self.try_to_find_city(self.payload["to"])

        if "court" in self.payload:
            self.payload["court"] = self.try_to_find_city(self.payload["court"])

        return self.payload


class SuccessorRelocationNotice(AbstractNotice):
    kls = "SuccessorRelocationNotice"
    kind = "notices"

    from_regex = re.compile(
        r"\bvon\s+([^\s]*\s?[^\s]*\s?[^\s]*\s?[^\s]*\s?)", flags=re.I
    )
    hrb_regex = re.compile(
        r"\b((?:HR\s?[AB]|VR|GnR|PR)\s?\d+\s?\b[A-Z]{0,3}\b)", flags=re.I
    )

    to_regex = re.compile(
        r"\bnach\s+([^\s]*\s?[^\s]*\s?[^\s]*\s?[^\s]*\s?)", flags=re.I
    )
    to_regex2 = re.compile(
        r"\bNeuer\s+Sitz:?\s+([^\s]*\s?[^\s]*\s?[^\s]*\s?[^\s]*\s?)", flags=re.I
    )
    court_regex = re.compile(
        r"\b(?:AG|Amtsgericht)\s+([^\s]*\s?[^\s]*\s?[^\s]*\s?[^\s]*\s?)", flags=re.I
    )

    def __init__(self, text, doc=None):
        self.text = text
        self.payload = {
            "used_regex": [],
            "text": text,
            "court": None,
            "registration": self.identify_notice_type(),
        }

        matches = self.from_regex.search(text)
        if matches and matches.group(1):
            self.payload["from"] = matches.group(1).strip()
            self.payload["used_regex"].append("from_regex")

        matches = self.hrb_regex.search(text)
        if matches and matches.group(1):
            self.payload["hrb"] = matches.group(1).strip()
            self.payload["used_regex"].append("hrb_regex")

        matches = self.to_regex.search(text)
        if matches and matches.group(1):
            self.payload["to"] = matches.group(1).strip()
            self.payload["used_regex"].append("to_regex")
        else:
            matches = self.to_regex2.search(text)
            if matches and matches.group(1):
                self.payload["to"] = matches.group(1).strip()
                self.payload["used_regex"].append("to_regex2")

        matches = self.court_regex.search(text)
        if matches and matches.group(1):
            self.payload["court"] = matches.group(1).strip()
            self.payload["used_regex"].append("court_regex")

        if self.payload["registration"] is None:
            self.try_to_deduct_registration()

        if (
            doc.get("event_type").lower() in ["löschungen", "veränderungen"]
            and self.payload["registration"] == "successor"
        ):
            self.payload["registration_conflict"] = True


class PredecessorRelocationNotice(AbstractNotice):
    kls = "PredecessorRelocationNotice"
    kind = "notices"

    from_hrb_to_regex = re.compile(
        r"\bvon\s+([^\(]+).*((?:HR\s?[AB]|VR|GnR|PR)\s?\d+\s?\b[A-Z]{0,3}\b).*nach\W([^\s]*\s?[^\s]*\s?[^\s]*\s?[^\s]*\s?)",
        flags=re.I,
    )

    from_hrb_regex = re.compile(
        r"\bvon\s+([^\(]+).*((?:HR\s?[AB]|VR|GnR|PR)\s?\d+\s?\b[A-Z]{0,3}\b)",
        flags=re.I,
    )
    from_regex = re.compile(
        r"\bvon\s+([^\s]*\s?[^\s]*\s?[^\s]*\s?[^\s]*\s?)", flags=re.I
    )
    hrb_regex = re.compile(
        r"\b((?:HR\s?[AB]|VR|GnR|PR)\s?\d+\s?\b[A-Z]{0,3}\b)", flags=re.I
    )
    to_regex = re.compile(
        r"\bnach\s+([^\s]*\s?[^\s]*\s?[^\s]*\s?[^\s]*\s?)", flags=re.I
    )

    court_regex = re.compile(
        r"\b(?:AG|Amtsgericht)\s+([^\s]*\s?[^\s]*\s?[^\s]*\s?[^\s]*\s?)", flags=re.I
    )

    def __init__(self, text, doc=None):
        self.text = text

        self.payload = {
            "used_regex": [],
            "text": text,
            "court": None,
            "registration": self.identify_notice_type(),
        }

        court_matches = self.court_regex.search(text)
        if court_matches and court_matches.group(1):
            self.payload["court"] = court_matches.group(1).strip()
            self.payload["used_regex"].append("court_regex")

        matches = self.from_hrb_to_regex.search(text)
        if matches:
            self.payload["from"] = matches.group(1).strip()
            self.payload["hrb"] = matches.group(2).strip()
            self.payload["to"] = matches.group(3).strip()
            self.payload["used_regex"].append("from_hrb_to_regex")
        else:
            matches = self.from_hrb_regex.search(text)
            if matches:
                self.payload["from"] = matches.group(1).strip()
                self.payload["hrb"] = matches.group(2).strip()
                self.payload["used_regex"].append("from_hrb_regex")

                matches = self.to_regex.search(text)
                if matches:
                    self.payload["to"] = matches.group(1).strip()
                    self.payload["used_regex"].append("to_regex")
            else:
                matches = self.from_regex.search(text)
                if matches:
                    self.payload["from"] = matches.group(1).strip()
                    self.payload["used_regex"].append("from")

                matches = self.hrb_regex.search(text)
                if matches:
                    self.payload["hrb"] = matches.group(1).strip()
                    self.payload["used_regex"].append("hrb")

                matches = self.to_regex.search(text)
                if matches:
                    self.payload["to"] = matches.group(1).strip()
                    self.payload["used_regex"].append("to_regex")

        if self.payload["registration"] is None:
            self.try_to_deduct_registration()

        if (
            doc.get("event_type").lower() in ["neueintragungen"]
            and self.payload["registration"] == "predecessor"
        ):
            self.payload["registration_conflict"] = True


class Sentence(object):
    __slots__ = [
        "text",
        "split",
        "convert_to_flag",
        "assign_label_to_postfix",
        "capture_whole_text",
    ]

    def __init__(
        self,
        text,
        split=False,
        convert_to_flag=None,
        assign_label_to_postfix=None,
        capture_whole_text=False,
    ):
        if isinstance(text, str):
            self.text = re.escape(text)
        else:
            self.text = text

        self.split = split
        self.convert_to_flag = convert_to_flag
        self.assign_label_to_postfix = assign_label_to_postfix
        self.capture_whole_text = capture_whole_text

    def parse(self, sentence, doc):
        text = None

        if isinstance(self.text, str):
            text = self.text
        else:
            m = self.text.search(sentence)
            if m:
                text = re.escape(m.group(0))

        if text is None or not re.search(text, sentence, flags=re.I | re.U):
            yield
        else:
            try:
                if self.convert_to_flag is not None:
                    if self.capture_whole_text:
                        yield Flag(self.convert_to_flag, sentence)
                    else:
                        yield Flag(self.convert_to_flag, text)

                if self.split:
                    for x in sentence.split(text, 1):
                        yield x

                if self.assign_label_to_postfix is not None:
                    prefix, postfix = re.split(text, sentence, 1, flags=re.I | re.U)

                    if isinstance(self.assign_label_to_postfix, str):
                        yield Label(self.assign_label_to_postfix, postfix)
                    elif isinstance(self.assign_label_to_postfix, type):
                        yield self.assign_label_to_postfix(postfix, doc)
            except ParsingError as e:
                yield Error(type(e).__name__, str(e))


sentences = [
    Sentence(
        "Nicht mehr Geschäftsführer:", assign_label_to_postfix=DismissedManagingDirector
    ),
    Sentence(
        "Nicht mehr Geschäftsführerin:",
        assign_label_to_postfix=DismissedManagingDirector,
    ),
    Sentence(
        "Ausgeschieden: Geschäftsführer:",
        assign_label_to_postfix=RetiredManagingDirector,
    ),
    Sentence(
        "Ausgeschieden Geschäftsführer:",
        assign_label_to_postfix=RetiredManagingDirector,
    ),
    Sentence(
        "Ausgeschieden als Persönlich haftender Gesellschafter:",
        assign_label_to_postfix=RetiredPersonalPartner,
    ),
    Sentence(
        "Ausgeschieden: Persönlich haftender Gesellschafter:",
        assign_label_to_postfix=RetiredPersonalPartner,
    ),
    Sentence(
        "Bestellt als Geschäftsführer:",
        assign_label_to_postfix=AppointedManagingDirector,
    ),
    Sentence(
        "Bestellt: Geschäftsführer:", assign_label_to_postfix=AppointedManagingDirector
    ),
    Sentence(
        "Bestellt Geschäftsführer:", assign_label_to_postfix=AppointedManagingDirector
    ),
    Sentence(
        "Ausgeschieden: Geschäftsführer:", assign_label_to_postfix=RetiredManagingDirector
    ),
    Sentence(
        "director:", assign_label_to_postfix=ManagingDirector
    ),
    Sentence("Geändert, nun: Liquidator", assign_label_to_postfix=Liquidator),
    Sentence("Nicht mehr Liquidator", assign_label_to_postfix=NotALiquidator),
    Sentence("Geschäftsführer:", assign_label_to_postfix=ManagingDirector),
    Sentence("Geschäftsführerin:", assign_label_to_postfix=ManagingDirector),
    Sentence("Einzelprokura:", assign_label_to_postfix=SingleProcuration),
    Sentence("Prokura:", assign_label_to_postfix=Procuration),
    Sentence("Bestellt Vorstand:", assign_label_to_postfix=AppointedBoard),
    Sentence("Ausgeschieden Vorstand:", assign_label_to_postfix=RemovedFromBoard),
    Sentence("Nicht mehr Prokurist:", assign_label_to_postfix=NotAProcurator),
    Sentence(
        "Einzelprokura mit der Befugnis im Namen der Gesellschaft mit sich im eigenen Namen oder als Vertreter eines Dritten Rechtsgeschäfte abzuschließen:",
        assign_label_to_postfix=SingleProcuration,
    ),
    Sentence(
        "Bestellt als einzelvertretungsberechtigte Geschäftsführerin mit der Befugnis im Namen der Gesellschaft mit sich im eigenen Namen oder als Vertreter eines Dritten Rechtsgeschäfte abzuschließen:",
        assign_label_to_postfix=FullPerson,
    ),
    Sentence(
        "Gesamtprokura gemeinsam mit einem anderen Prokuristen mit der Befugnis, im Namen der Gesellschaft mit sich als Vertreter der persönlich haftenden Gesellschafterin Rechtsgeschäfte abzuschließen",
        assign_label_to_postfix=FullPerson,
    ),
    Sentence(
        # TODO: translate and check if can be merged with flag above
        "Einzelprokura mit der Befugnis, im Namen der Gesellschaft mit sich im eigenen Namen oder als Vertreter eines Dritten Rechtsgeschäfte abzuschließen:",
        assign_label_to_postfix=SingleProcuration,
    ),
    Sentence(
        # TODO: translate and check if can be merged with flag above
        "Einzelprokura mit der Befugnis, im Namen der Gesellschaft mit sich als Vertreter eines Dritten Rechtsgeschäfte abzuschließen:",
        assign_label_to_postfix=SingleProcuration,
    ),
    Sentence(
        "Persönlich haftender Gesellschafter:", assign_label_to_postfix=PersonalPartner
    ),
    Sentence(
        "Gesamtprokura gemeinsam mit einem Geschäftsführer oder einem anderen Prokuristen:",
        assign_label_to_postfix=CommonProcuration,
    ),
    Sentence(
        "Gesamtprokura gemeinsam mit einem Vorstandsmitglied oder einem anderen Prokuristen:",
        assign_label_to_postfix=CommonProcuration,
    ),
    Sentence(
        re.compile(r"Prokura geändert(.*):", re.I),
        assign_label_to_postfix=NewProcuration,
    ),
    Sentence("Inhaber:", assign_label_to_postfix=Owner),
    Sentence("Nicht mehr Inhaber:", assign_label_to_postfix=NotLongerOwner),
    Sentence("Liquidator:", assign_label_to_postfix=Liquidator),
    Sentence("Prokura erloschen:", assign_label_to_postfix=ProcurationCancelled),
    Sentence("Sitz / Zweigniederlassung:", assign_label_to_postfix="company"),
    Sentence("B:", assign_label_to_postfix="WHUT"),
    Sentence("Stamm - bzw. Grundkapital:", assign_label_to_postfix="misc"),
    Sentence("Geschäftsanschrift:", assign_label_to_postfix="address"),
    Sentence(
        "mit der Befugnis die Gesellschaft allein zu vertreten mit der Befugnis Rechtsgeschäfte mit sich selbst oder als Vertreter Dritter abzuschließen",
        convert_to_flag="with the power to represent the company alone with the power to conclude legal transactions with itself or as a representative of third parties",
    ),
    Sentence(
        "Alleinvertretungsbefugnis kann erteilt werden.",
        convert_to_flag="Exclusive power of representation can be granted.",
    ),
    Sentence(
        "Sind mehrere Geschäftsführer bestellt, wird die Gesellschaft gemeinschaftlich durch zwei Geschäftsführer oder durch einen Geschäftsführer in Gemeinschaft mit einem Prokuristen vertreten.",
        convert_to_flag="If several directors are appointed, the company will be jointly represented by two directors or by a managing director in company with an authorized signatory.",
    ),
    Sentence(
        "mit der Befugnis Rechtsgeschäfte mit sich selbst oder als Vertreter Dritter abzuschließen",
        convert_to_flag="with the power to conclude legal transactions with itself or as a representative of third parties",
    ),
    Sentence(
        "Gesellschaft mit beschränkter Haftung.",
        convert_to_flag="Company with limited liability.",
    ),
    Sentence(
        "mit der Befugnis, im Namen der Gesellschaft mit sich im eigenen Namen oder als Vertreter eines Dritten Rechtsgeschäfte abzuschließen.",
        convert_to_flag="with the power to enter into legal transactions on behalf of the Company with itself or as a representative of a third party",
    ),
    Sentence(
        "Sind mehrere Geschäftsführer bestellt, so wird die Gesellschaft durch zwei Geschäftsführer oder durch einen Geschäftsführer gemeinsam mit einem Prokuristen vertreten.",
        convert_to_flag="If several managing directors are appointed, then the company is represented by two managing directors or by a managing director together with an authorized officer.",
    ),
    Sentence(
        "mit der Befugnis die Gesellschaft allein zu vertreten",
        convert_to_flag="with the power to represent the company alone",
    ),
    Sentence(
        "Sind mehrere Geschäftsführer bestellt, wird die Gesellschaft durch sämtliche Geschäftsführer gemeinsam vertreten.",
        convert_to_flag="If several managing directors are appointed, the company is jointly represented by all managing directors.",
    ),
    Sentence(
        "Ist nur ein Geschäftsführer bestellt, so vertritt er die Gesellschaft allein.",
        convert_to_flag="If only one managing director is appointed, he represents the company alone.",
    ),
    Sentence("Die Gesellschaft ist aufgelöst.", convert_to_flag="CompanyClosed"),
    Sentence("Einzelprokura", convert_to_flag="Single procuration"),
    Sentence("Einzelkaufmann", assign_label_to_postfix=FullPerson),
    Sentence("Einzelkaufmann", convert_to_flag="Sole trader"),
    Sentence(
        re.compile(r"\bSitzverlegung\b", flags=re.I),
        assign_label_to_postfix=PredecessorRelocationNotice,
    ),
    Sentence(
        re.compile(r"\bDer\s+Sitz\b", flags=re.I),
        assign_label_to_postfix=SuccessorRelocationNotice,
    ),
    Sentence(
        re.compile(r"\bSitz\s+verlegt\b", flags=re.I),
        assign_label_to_postfix=SuccessorRelocationNotice,
    ),
    Sentence("Der Inhaber handelt allein", convert_to_flag="The owner is acting alone"),
    Sentence("Kommanditgesellschaft.", convert_to_flag="Limited partnership."),
    Sentence(
        "Sind mehrere Liquidatoren bestellt, wird die Gesellschaft durch sämtliche Liquidatoren gemeinsam vertreten.",
        convert_to_flag="If several liquidators are appointed, the company will be represented jointly by all liquidators.",
    ),

    Sentence("Bestellt als Vorstand", assign_label_to_postfix=AppointedManagingDirector),
    Sentence("Nicht mehr Vorstand", assign_label_to_postfix=RetiredBoard),
    Sentence("Nicht mehr Vorstand:", assign_label_to_postfix=RetiredBoard),
    Sentence("Bestellt zum Vorstand:", assign_label_to_postfix=AppointedBoard),
]

sentences = sorted(
    sentences,
    key=lambda x: len(x.text) if isinstance(x.text, str) else 1000,
    reverse=True,
)


def _parse_normalized(sents: tuple, doc: dict):
    for sent in [sents]:
        sent_had_persons = False

        for chunk in sent.split(";"):
            normalized = re.sub(r"\s+", " ", chunk)

            chunk_had_persons = False
            chunk_had_relocation = False
            for known_sentence in sentences:
                res = list(filter(None, known_sentence.parse(normalized, doc)))
                if res:
                    for r in res:
                        if isinstance(r, FullPerson):
                            if not sent_had_persons:
                                sent_had_persons = r

                            if chunk_had_persons:
                                continue
                            else:
                                chunk_had_persons = True

                        if isinstance(r, AbstractNotice):
                            if chunk_had_relocation:
                                continue
                            else:
                                chunk_had_relocation = True
                        yield r

            if sent_had_persons and not chunk_had_persons and not chunk_had_relocation:
                try:
                    person = type(sent_had_persons)(chunk, doc)
                    yield person
                except ParsingError as e:
                    yield Error(type(e).__name__, str(e))


def parse_document(doc: dict) -> (defaultdict, dict):
    errors = []
    text = doc.get("full_text", "")  # type: str
    event_type = doc.get("event_type", None)  # type: str

    if event_type and event_type in text:
        _, useful_text = text.split(event_type, 1)  # type: (str, str)
    else:
        try:
            _, useful_text = _useful_regex.split(text, 1)  # type: (str, str)
        except ValueError:
            errors.append("Cannot parse an event type out of text {}".format(text))
            useful_text = text  # type: str

    useful_text = useful_text.replace(":; ", ": ")
    useful_text = useful_text.replace(", geb.", " geborene")
    useful_text = useful_text.replace(" geb.", " geborene")
    useful_text = useful_text.replace(", geborene", " geborene")
    useful_text = useful_text.replace(" geborener", " geborene")
    useful_text = useful_text.replace(" Dr.-Ing.", " Doktoringenieur")
    useful_text = useful_text.replace(" Dipl.-Ing.", " Diplomingenieur")
    useful_text = useful_text.replace(" Dr.", " Doctor")
    useful_text = useful_text.replace(" Prof.", " Professor")
    useful_text = useful_text.replace(" Dipl.-Betriebswirt", " Diplombetriebswirt")
    useful_text = useful_text.replace(" Dipl.-Kauffrau", " Diplomkauffrau")
    useful_text = useful_text.replace(" Dipl.-Kfm", " Diplomkfm")

    useful_text = re.sub(r":\s(\d+)\.", r":\1)", useful_text)
    sents = _german_tokenizer.tokenize(useful_text)  # type: tuple
    res = defaultdict(list)

    if errors:
        res["errors"] = errors

    for v in chain.from_iterable(
        map(lambda x: _parse_normalized(x, doc), sents)
    ):
        res[v.kind].append(v.to_dict())

    return res, doc
