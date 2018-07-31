# coding=utf-8
import os.path
import re
from collections import defaultdict
from itertools import chain

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
    translations = {
        "einzelvertretungsberechtigt": "sole representation",
        "mit der befugnis, im namen der gesellschaft mit sich im eigenen namen oder als vertreter eines dritten rechtsgeschäfte abzuschließen":
        "with the power to enter into legal transactions on behalf of the Company with itself or as a representative of a third party"
    }

    @staticmethod
    def parse_dob(dob):
        m = dob_regex.search(dob.strip(" ;."))

        if m:
            return dt_parse(m.group(0).strip("* ;.")).date()
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

    def __init__(self, text):
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
                if " gmbh" in self.text.lower() or " mbh" in self.text.lower():
                    self.company_name = self.text
                    self.payload = {
                        "company_name": self.company_name,
                    }
                else:
                    if len(chunks) == 2:
                        self.lastname = chunks[0].strip(" *;.")
                        self.name = chunks[1].strip(" *;.")
                        self.payload = {
                            "name": self.name,
                            "lastname": self.lastname,
                        }
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
                        raise ValueError("a person without DOB, number of chunks: {}".format(len(chunks)))
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
                raise ValueError("no valid patter found, number of chunks: {}".format(len(chunks)))
        except ValueError as e:
            raise ParsingError("Cannot parse a {} from {}, error text was {}".format(self.kls, text, e))

    def to_dict(self):
        if "lastname" in self.payload:
            if "geborene" in self.payload["lastname"]:
                self.payload["lastname"], self.payload["maidenname"] = self.payload["lastname"].split(" geborene", 1)
                self.payload["maidenname"] = self.payload["maidenname"].replace("geborene", "").strip()
                self.payload["lastname"] = self.payload["lastname"].strip()
                self.payload["maidenname"] = self.payload["maidenname"].strip()

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


class Sentence(object):
    __slots__ = ["text", "split", "convert_to_flag", "assign_label_to_postfix"]

    def __init__(
        self, text, split=False, convert_to_flag=None, assign_label_to_postfix=None
    ):
        if isinstance(text, str):
            self.text = re.escape(text)
        else:
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
                text = re.escape(m.group(0))

        if text is None or not re.search(text, sentence, flags=re.I | re.U):
            yield
        else:
            try:
                if self.convert_to_flag is not None:
                    yield Flag(self.convert_to_flag, text)

                if self.split:
                    for x in sentence.split(text, 1):
                        yield x

                if self.assign_label_to_postfix is not None:
                    prefix, postfix = re.split(text, sentence, 1, flags=re.I | re.U)

                    # if prefix.strip() and isinstance(self.assign_label_to_postfix, type):
                    #     print("'{}'".format(prefix + text))

                    if isinstance(self.assign_label_to_postfix, str):
                        yield Label(self.assign_label_to_postfix, postfix)
                    elif isinstance(self.assign_label_to_postfix, type):
                        yield self.assign_label_to_postfix(postfix)
            except ParsingError as e:
                yield Error(type(e).__name__, str(e))


sentences = [
    Sentence("Nicht mehr Geschäftsführer:", assign_label_to_postfix=DismissedManagingDirector),
    Sentence("Nicht mehr Geschäftsführerin:", assign_label_to_postfix=DismissedManagingDirector),
    Sentence("Ausgeschieden: Geschäftsführer:", assign_label_to_postfix=RetiredManagingDirector),
    Sentence("Ausgeschieden Geschäftsführer:", assign_label_to_postfix=RetiredManagingDirector),
    Sentence("Ausgeschieden als Persönlich haftender Gesellschafter:", assign_label_to_postfix=RetiredPersonalPartner),
    Sentence("Ausgeschieden: Persönlich haftender Gesellschafter:", assign_label_to_postfix=RetiredPersonalPartner),

    Sentence("Bestellt als Geschäftsführer:", assign_label_to_postfix=AppointedManagingDirector),
    Sentence("Bestellt: Geschäftsführer:", assign_label_to_postfix=AppointedManagingDirector),
    Sentence("Bestellt Geschäftsführer:", assign_label_to_postfix=AppointedManagingDirector),

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
    Sentence("Die Gesellschaft ist aufgelöst.", convert_to_flag="ignore_for_now"),
    Sentence("Einzelprokura", convert_to_flag="Single procuration"),
    Sentence("Einzelkaufmann", convert_to_flag="Sole trader"),
    Sentence("Der Inhaber handelt allein", convert_to_flag="The owner is acting alone"),
    Sentence("Kommanditgesellschaft.", convert_to_flag="Limited partnership."),
    Sentence(
        "Sind mehrere Liquidatoren bestellt, wird die Gesellschaft durch sämtliche Liquidatoren gemeinsam vertreten.",
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
            # yield " ".join(tokenize_words(chunk))
            # yield chunk
            yield re.sub(r"\s+", " ", chunk)


def _parse_normalized(normalized: str):
    should_break = False
    for known_sentence in sentences:
        res = list(filter(None, known_sentence.parse(normalized)))
        if res:
            for r in res:
                if isinstance(r, FullPerson):
                    should_break = True
                yield r

        if should_break:
            break


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

    useful_text = useful_text.replace(":; ", ": ")
    useful_text = useful_text.replace(", geb.", " geborene")
    useful_text = useful_text.replace(" geb.", " geborene")
    useful_text = useful_text.replace(" Dr.-Ing.", " Doktoringenieur")
    useful_text = useful_text.replace(" Dipl.-Ing.", " Diplomingenieur")
    useful_text = useful_text.replace(" Dr.", " Doctor")
    useful_text = re.sub(r":\s\d+\.", ":", useful_text)
    sents = _german_tokenizer.tokenize(useful_text)  # type: tuple
    res = defaultdict(list)

    if errors:
        res["errors"] = errors

    for v in chain.from_iterable(map(_parse_normalized, _get_normalized(sents))):
        res[v.kind].append(v.to_dict())

    return res, sents
