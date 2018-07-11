import re
import os.path
from nltk import data
from dateutil.parser import parse as dt_parse
from tokenize_uk import tokenize_words

german_tokenizer = data.load(
    os.path.join(os.path.dirname(__file__), "data/german.pickle"))


class Flag(object):
    __slots__ = ["flag", "text"]

    def __init__(self, flag, text):
        self.flag = flag
        self.text = text

    def to_dict(self):
        return {
            "flag": self.flag,
            "text": self.text
        }

    def __str__(self):
        return "[Flag: {} ({})]".format(self.flag, self.text)


class Label(object):
    __slots__ = ["label", "text"]

    def __init__(self, label, text):
        self.label = label
        self.text = text

    def to_dict(self):
        return {
            "label": self.label,
            "text": self.text
        }

    def __str__(self):
        return "[Label/{}: {}]".format(self.label, self.text)


class FullPerson(object):
    kls = "Person"
    translations = {
        "einzelvertretungsberechtigt": "sole representation"
    }

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
                self.dob = chunks[3].strip(" *;.")
                self.payload = {
                    "name": self.name,
                    "lastname": self.lastname,
                    "city": self.city,
                    "dob": dt_parse(self.dob).date()
                }
                self.description = "\nFirstname: {},\nLastname: {},\nCity: {},\nDOB: {}".format(
                    self.name,
                    self.lastname,
                    self.city,
                    dt_parse(self.dob).date()
                )
            if len(chunks) == 5:
                self.lastname = chunks[0].strip(" *;.")
                self.name = chunks[1].strip(" *;.")
                self.city = chunks[2].strip(" *;.")
                self.dob = chunks[3].strip(" *;.")
                self.flag = chunks[4].strip(" *;.")
                if self.flag in self.translations:
                    self.flag = self.translations[self.flag]

                self.payload = {
                    "name": self.name,
                    "lastname": self.lastname,
                    "city": self.city,
                    "dob": dt_parse(self.dob).date(),
                    "flag": self.flag
                }
                self.description = "\nFirstname: {},\nLastname: {},\nCity: {},\nDOB: {},\nFlag: {}".format(
                    self.name,
                    self.lastname,
                    self.city,
                    dt_parse(self.dob).date(),
                    self.flag
                )
            elif len(chunks) == 3:
                self.lastname = chunks[0].strip(" *;.")
                self.name = chunks[1].strip(" *;.")
                self.dob = chunks[-1].strip(" *;.")

                self.payload = {
                    "name": self.name,
                    "lastname": self.lastname,
                    "dob": self.dob
                }
                self.description = "\nFirstname: {},\nLastname: {},\nDOB: {}".format(
                    self.name,
                    self.lastname,
                    dt_parse(self.dob).date()
                )
        except ValueError:
            print("Cannot parse {}".format(text))            

    def to_dict(self):
        return {
            "class": self.kls,
            "text": self.text,
            "payload": self.payload
        }

    def __str__(self):
        if self.description:
            return "[{}: {}] {}".format(self.kls, self.text, self.description)
        else:
            return "[{}: {}]".format(self.kls, self.text)


class ManagingDirector(FullPerson):
    kls = "ManagingDirector"


class Owner(FullPerson):
    kls = "Owner"


class Sentence(object):
    __slots__ = ["text", "split", "convert_to_flag", "assign_label_to_postfix"]

    def __init__(self, text, split=False, convert_to_flag=None, assign_label_to_postfix=None):
        self.text = text
        self.split = split
        self.convert_to_flag = convert_to_flag
        self.assign_label_to_postfix = assign_label_to_postfix

    def parse(self, sentence):
        if self.text not in sentence:
            yield
        else:
            if self.convert_to_flag is not None:
                yield Flag(self.convert_to_flag, self.text)

            if self.split:
                for x in sentence.split(self.text, 1):
                    yield x

            if self.assign_label_to_postfix is not None:
                _, postfix = sentence.split(self.text, 1)

                if isinstance(self.assign_label_to_postfix, str):
                    yield Label(self.assign_label_to_postfix, postfix)
                elif isinstance(self.assign_label_to_postfix, type):
                    yield self.assign_label_to_postfix(postfix)


sentences = [
    Sentence("Geschäftsführer :", assign_label_to_postfix=ManagingDirector),
    Sentence("Inhaber :", assign_label_to_postfix=Owner),
    Sentence("Sitz / Zweigniederlassung :", assign_label_to_postfix="company"),
    Sentence("B :", assign_label_to_postfix="WHUT"),
    Sentence("Stamm - bzw . Grundkapital :", assign_label_to_postfix="misc"),
    Sentence("Geschäftsanschrift :", assign_label_to_postfix="address"),
    Sentence("mit der Befugnis die Gesellschaft allein zu vertreten mit der Befugnis Rechtsgeschäfte mit sich selbst oder als Vertreter Dritter abzuschließen", convert_to_flag="with the power to represent the company alone with the power to conclude legal transactions with itself or as a representative of third parties"),
    Sentence("Alleinvertretungsbefugnis kann erteilt werden .", convert_to_flag="Exclusive power of representation can be granted."),
    Sentence("Sind mehrere Geschäftsführer bestellt , wird die Gesellschaft gemeinschaftlich durch zwei Geschäftsführer oder durch einen Geschäftsführer in Gemeinschaft mit einem Prokuristen vertreten .", convert_to_flag="If several directors are appointed, the company will be jointly represented by two directors or by a managing director in company with an authorized signatory."),
    Sentence("mit der Befugnis Rechtsgeschäfte mit sich selbst oder als Vertreter Dritter abzuschließen", convert_to_flag="with the power to conclude legal transactions with itself or as a representative of third parties"),
    Sentence("Gesellschaft mit beschränkter Haftung .", convert_to_flag="Company with limited liability ."),
    Sentence("mit der Befugnis , im Namen der Gesellschaft mit sich im eigenen Namen oder als Vertreter eines Dritten Rechtsgeschäfte abzuschließen .", convert_to_flag="with the power to enter into legal transactions on behalf of the Company with itself or as a representative of a third party"),
    Sentence("Sind mehrere Geschäftsführer bestellt , so wird die Gesellschaft durch zwei Geschäftsführer oder durch einen Geschäftsführer gemeinsam mit einem Prokuristen vertreten .", convert_to_flag="If several managing directors are appointed, then the company is represented by two managing directors or by a managing director together with an authorized officer."),
    Sentence("mit der Befugnis die Gesellschaft allein zu vertreten", convert_to_flag="with the power to represent the company alone"),
    Sentence("Sind mehrere Geschäftsführer bestellt , wird die Gesellschaft durch sämtliche Geschäftsführer gemeinsam vertreten .", convert_to_flag="If several managing directors are appointed, the company is jointly represented by all managing directors."),
    Sentence("Ist nur ein Geschäftsführer bestellt , so vertritt er die Gesellschaft allein .", convert_to_flag="If only one managing director is appointed, he represents the company alone."),
    Sentence("Die Gesellschaft ist aufgelöst .", convert_to_flag="ignore_for_now"),
    Sentence("Einzelprokura", convert_to_flag="Single procuration"),
    Sentence("Einzelkaufmann", convert_to_flag="Sole trader"),
    Sentence("Der Inhaber handelt allein", convert_to_flag="The owner is acting alone"),
    Sentence("Kommanditgesellschaft .", convert_to_flag="Limited partnership."),
    Sentence("Sind mehrere Liquidatoren bestellt , wird die Gesellschaft durch sämtliche Liquidatoren gemeinsam vertreten .", convert_to_flag="If several liquidators are appointed, the company will be represented jointly by all liquidators."),
]

sentences = sorted(sentences, key=lambda x: len(x.text), reverse=True)


def parse_document(doc):
    text = doc.get("full_text", "")
    if "event_type" in doc and doc["event_type"] in text:
        _, useful_text = text.split(doc["event_type"], 1)
    else:
        try:
            _, useful_text = re.split(r"\d{2}\.\d{2}\.\d{4}\n\n", text, 1, flags=re.M)
        except ValueError:
            print(text)
            useful_text = text

    sents = german_tokenizer.tokenize(useful_text)
    res = []
    for sent in sents:
        for chunk in sent.split(";"):
            tokenized = tokenize_words(chunk)
            normalized = " ".join(tokenized)
            for known_sentence in sentences:
                for parse_res in known_sentence.parse(normalized):
                    if parse_res:
                        res.append(parse_res)
    return res, sents
