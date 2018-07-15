# coding=utf-8
import os.path
import re
from collections import defaultdict

from dateutil.parser import parse as dt_parse
from nltk import data
from tokenize_uk import tokenize_words

_german_tokenizer = data.load(os.path.join(os.path.dirname(__file__),
                                           "data/german.pickle"))
dob_regex = re.compile(r"\*\s?\d{2}\s?\.\s?\d{2}\s?.\s?\d{4}")
_useful_regex = re.compile(r"\d{2}\.\d{2}\.\d{4}\n\n", flags=re.M)


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
    translations = {"einzelvertretungsberechtigt": "sole representation"}

    @staticmethod
    def parse_dob(dob):
        m = dob_regex.search(dob.strip(" ;."))

        if m:
            return dt_parse(m.group(0).strip("* ;.")).date()
        else:
            raise ValueError()

    def __init__(self, text):
        self.text = text
        chunks = text.split(",")
        self.description = ""
        self.payload = {}

        try:
            if len(chunks) == 4:
                self.lastname = chunks[0].strip(" *;.")
                self.name = chunks[1].strip(" *;.")
                self.city = chunks[2].strip(" *;.")
                self.dob = self.parse_dob(chunks[3])
                self.payload = {
                    "name": self.name,
                    "lastname": self.lastname,
                    "city": self.city,
                    "dob": self.dob,
                }
                self.description = "\nFirstname: {},\nLastname: {},\nCity: {},\nDOB: {}".format(
                    self.name, self.lastname, self.city, self.dob
                )
            if len(chunks) == 5:
                self.lastname = chunks[0].strip(" *;.")
                self.name = chunks[1].strip(" *;.")
                self.city = chunks[2].strip(" *;.")
                self.dob = self.parse_dob(chunks[3])
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
                self.description = "\nFirstname: {},\nLastname: {},\nCity: {},\nDOB: {},\nFlag: {}".format(
                    self.name, self.lastname, self.city, self.dob, self.flag
                )
            elif len(chunks) == 3:
                self.lastname = chunks[0].strip(" *;.")
                self.name = chunks[1].strip(" *;.")
                self.dob = self.parse_dob(chunks[-1])

                self.payload = {
                    "name": self.name,
                    "lastname": self.lastname,
                    "dob": self.dob,
                }
                self.description = "\nFirstname: {},\nLastname: {},\nDOB: {}".format(
                    self.name, self.lastname, self.dob
                )
        except ValueError:
            raise ParsingError("Cannot parse a {} from {}".format(self.kls, text))

    def to_dict(self):
        return {"class": self.kls, "text": self.text, "payload": self.payload}

    def __str__(self):
        if self.description:
            return "[{}: {}] {}".format(self.kls, self.text, self.description)
        else:
            return "[{}: {}]".format(self.kls, self.text)


class ManagingDirector(FullPerson):
    kls = "ManagingDirector"


class Owner(FullPerson):
    kls = "Owner"


class SingleProcuration(FullPerson):
    kls = "SingleProcuration"


class NewProcuration(FullPerson):
    kls = "NewProcuration"


class PersonalPartner(FullPerson):
    kls = "PersonalPartner"


class Liquidator(FullPerson):
    kls = "Liquidator"


class ProcurationCancelled(FullPerson):
    kls = "ProcurationCancelled"


class CommonProcuration(FullPerson):
    kls = "CommonProcuration"


class NotAProcurator(FullPerson):
    kls = "NotAProcurator"


class RemovedFromBoard(FullPerson):
    kls = "RemovedFromBoard"


class AppointedBoard(FullPerson):
    kls = "AppointedBoard"


class Sentence(object):
    __slots__ = ["text", "split", "convert_to_flag", "assign_label_to_postfix"]

    def __init__(
        self, text, split=False, convert_to_flag=None, assign_label_to_postfix=None
    ):
        self.text = text
        self.split = split
        self.convert_to_flag = convert_to_flag
        self.assign_label_to_postfix = assign_label_to_postfix

    def parse(self, sentence):
        text = None

        if isinstance(self.text, str):
            text = self.text
        else:
            m = self.text.search(sentence)
            if m:
                text = m.group(0)

        if text is None or text not in sentence:
            yield
        else:
            try:
                if self.convert_to_flag is not None:
                    yield Flag(self.convert_to_flag, text)

                if self.split:
                    for x in sentence.split(text, 1):
                        yield x

                if self.assign_label_to_postfix is not None:
                    _, postfix = sentence.split(text, 1)

                    if isinstance(self.assign_label_to_postfix, str):
                        yield Label(self.assign_label_to_postfix, postfix)
                    elif isinstance(self.assign_label_to_postfix, type):
                        yield self.assign_label_to_postfix(postfix)
            except ParsingError as e:
                yield Error(type(e).__name__, str(e))


sentences = [
    # TODO: remove lowercased ones
    Sentence("Geschäftsführer :", assign_label_to_postfix=ManagingDirector),
    Sentence("geschäftsführer :", assign_label_to_postfix=ManagingDirector),
    Sentence("Geschäftsführerin :", assign_label_to_postfix=ManagingDirector),
    Sentence("geschäftsführerin :", assign_label_to_postfix=ManagingDirector),
    Sentence("Einzelprokura :", assign_label_to_postfix=SingleProcuration),
    Sentence("einzelprokura :", assign_label_to_postfix=SingleProcuration),
    Sentence("Bestellt Vorstand :", assign_label_to_postfix=AppointedBoard),
    Sentence("bestellt vorstand :", assign_label_to_postfix=AppointedBoard),
    Sentence("Ausgeschieden Vorstand :", assign_label_to_postfix=RemovedFromBoard),
    Sentence("ausgeschieden vorstand :", assign_label_to_postfix=RemovedFromBoard),
    Sentence("Nicht mehr Prokurist :", assign_label_to_postfix=NotAProcurator),
    Sentence("nicht mehr prokurist :", assign_label_to_postfix=NotAProcurator),
    Sentence(
        "Einzelprokura mit der Befugnis im Namen der Gesellschaft mit sich im eigenen Namen oder als Vertreter eines Dritten Rechtsgeschäfte abzuschließen :",
        assign_label_to_postfix=SingleProcuration,
    ),
    Sentence(
        "einzelprokura mit der befugnis im namen der gesellschaft mit sich im eigenen namen oder als vertreter eines dritten rechtsgeschäfte abzuschließen :",
        assign_label_to_postfix=SingleProcuration,
    ),
    Sentence(
        "Persönlich haftender Gesellschafter :", assign_label_to_postfix=PersonalPartner
    ),
    Sentence(
        "persönlich haftender gesellschafter :", assign_label_to_postfix=PersonalPartner
    ),
    Sentence(
        "Gesamtprokura gemeinsam mit einem Geschäftsführer oder einem anderen Prokuristen :",
        assign_label_to_postfix=CommonProcuration,
    ),
    Sentence(
        "gesamtprokura gemeinsam mit einem geschäftsführer oder einem anderen prokuristen :",
        assign_label_to_postfix=CommonProcuration,
    ),
    Sentence(
        re.compile(r"Prokura geändert(.*):", re.I),
        assign_label_to_postfix=NewProcuration,
    ),
    Sentence("Inhaber :", assign_label_to_postfix=Owner),
    Sentence("inhaber :", assign_label_to_postfix=Owner),
    Sentence("Liquidator :", assign_label_to_postfix=Liquidator),
    Sentence("liquidator :", assign_label_to_postfix=Liquidator),
    Sentence("Prokura erloschen :", assign_label_to_postfix=ProcurationCancelled),
    Sentence("prokura erloschen :", assign_label_to_postfix=ProcurationCancelled),
    Sentence("Sitz / Zweigniederlassung :", assign_label_to_postfix="company"),
    Sentence("B :", assign_label_to_postfix="WHUT"),
    Sentence("Stamm - bzw . Grundkapital :", assign_label_to_postfix="misc"),
    Sentence("Geschäftsanschrift :", assign_label_to_postfix="address"),
    Sentence(
        "mit der Befugnis die Gesellschaft allein zu vertreten mit der Befugnis Rechtsgeschäfte mit sich selbst oder als Vertreter Dritter abzuschließen",
        convert_to_flag="with the power to represent the company alone with the power to conclude legal transactions with itself or as a representative of third parties",
    ),
    Sentence(
        "Alleinvertretungsbefugnis kann erteilt werden .",
        convert_to_flag="Exclusive power of representation can be granted.",
    ),
    Sentence(
        "Sind mehrere Geschäftsführer bestellt , wird die Gesellschaft gemeinschaftlich durch zwei Geschäftsführer oder durch einen Geschäftsführer in Gemeinschaft mit einem Prokuristen vertreten .",
        convert_to_flag="If several directors are appointed, the company will be jointly represented by two directors or by a managing director in company with an authorized signatory.",
    ),
    Sentence(
        "mit der Befugnis Rechtsgeschäfte mit sich selbst oder als Vertreter Dritter abzuschließen",
        convert_to_flag="with the power to conclude legal transactions with itself or as a representative of third parties",
    ),
    Sentence(
        "Gesellschaft mit beschränkter Haftung .",
        convert_to_flag="Company with limited liability .",
    ),
    Sentence(
        "mit der Befugnis , im Namen der Gesellschaft mit sich im eigenen Namen oder als Vertreter eines Dritten Rechtsgeschäfte abzuschließen .",
        convert_to_flag="with the power to enter into legal transactions on behalf of the Company with itself or as a representative of a third party",
    ),
    Sentence(
        "Sind mehrere Geschäftsführer bestellt , so wird die Gesellschaft durch zwei Geschäftsführer oder durch einen Geschäftsführer gemeinsam mit einem Prokuristen vertreten .",
        convert_to_flag="If several managing directors are appointed, then the company is represented by two managing directors or by a managing director together with an authorized officer.",
    ),
    Sentence(
        "mit der Befugnis die Gesellschaft allein zu vertreten",
        convert_to_flag="with the power to represent the company alone",
    ),
    Sentence(
        "Sind mehrere Geschäftsführer bestellt , wird die Gesellschaft durch sämtliche Geschäftsführer gemeinsam vertreten .",
        convert_to_flag="If several managing directors are appointed, the company is jointly represented by all managing directors.",
    ),
    Sentence(
        "Ist nur ein Geschäftsführer bestellt , so vertritt er die Gesellschaft allein .",
        convert_to_flag="If only one managing director is appointed, he represents the company alone.",
    ),
    Sentence("Die Gesellschaft ist aufgelöst .", convert_to_flag="ignore_for_now"),
    Sentence("Einzelprokura", convert_to_flag="Single procuration"),
    Sentence("Einzelkaufmann", convert_to_flag="Sole trader"),
    Sentence("Der Inhaber handelt allein", convert_to_flag="The owner is acting alone"),
    Sentence("Kommanditgesellschaft .", convert_to_flag="Limited partnership."),
    Sentence(
        "Sind mehrere Liquidatoren bestellt , wird die Gesellschaft durch sämtliche Liquidatoren gemeinsam vertreten .",
        convert_to_flag="If several liquidators are appointed, the company will be represented jointly by all liquidators.",
    ),
]

sentences = sorted(
    sentences,
    key=lambda x: len(x.text) if isinstance(x.text, str) else 1000,
    reverse=True,
)


def _get_normalized(sents: tuple):
    for sent in sents:
        for chunk in sent.split(";"):
            yield " ".join(tokenize_words(chunk))


def _parse_normalized(normalized: str):
    for known_sentence in sentences:
        yield from filter(None, known_sentence.parse(normalized))


def parse_document(doc: dict) -> (defaultdict, tuple):
    errors = []
    text = doc.get("full_text", "")  # type: str
    event_type = doc.get("event_type", None)  # type: str

    if event_type in text:
        _, useful_text = text.split(event_type, 1)  # type: (str, str)
    else:
        try:
            _, useful_text = _useful_regex.split(text, 1)  # type: (str, str)
        except ValueError:
            errors.append("Cannot parse an event type out of text {}".format(text))
            useful_text = text  # type: str

    sents = _german_tokenizer.tokenize(useful_text)  # type: tuple
    res = defaultdict(list)

    if errors:
        res["errors"] = errors

    map(lambda v: res[v.kind].append(v), map(_parse_normalized, _get_normalized(sents)))

    return res, sents
