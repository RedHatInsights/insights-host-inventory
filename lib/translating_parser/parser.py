from prance import BaseParser

from .translator import RefTranslator


class TranslatingParser(BaseParser):
    def _validate(self):
        # Just as ResolvingParser, the magic happens in this function.
        # It's this one that processes and saves self.specification.
        translator = RefTranslator(self.specification, self.url)
        translator.translate_references()
        self.specification = translator.specs

        BaseParser._validate(self)
