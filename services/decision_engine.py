class DecisionEngine:

    def __init__(self, knowledge):
        self.knowledge = knowledge

    def search_sku(self, sku):

        if "SKU Рішення" not in self.knowledge:
            return None

        df = self.knowledge["SKU Рішення"]

        for _, row in df.iterrows():
            if sku.lower() in str(row.to_dict()).lower():
                return row.to_dict()

        return None

    def search_exceptions(self, sku):

        if "Виключення" not in self.knowledge:
            return None

        df = self.knowledge["Виключення"]

        for _, row in df.iterrows():
            if sku.lower() in str(row.to_dict()).lower():
                return row.to_dict()

        return None
