import re


def natural_sort_key(s: str):
    """
    Key for sorting strings containing numbers naturally.
    'file_2.pdf' comes before 'file_10.pdf'.
    """
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split("([0-9]+)", s)
    ]
