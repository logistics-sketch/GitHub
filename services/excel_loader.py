import pandas as pd

class KnowledgeBase:

    def __init__(self):
        self.audit = pd.ExcelFile("data/Аудит Рекламації.xlsx")
        self.solutions = pd.ExcelFile("data/База рішень.xlsx")

    def load_all(self):
        result = {}

        for sheet in self.audit.sheet_names:
            result[sheet] = pd.read_excel(self.audit, sheet_name=sheet)

        for sheet in self.solutions.sheet_names:
            result[sheet] = pd.read_excel(self.solutions, sheet_name=sheet)

        return result
