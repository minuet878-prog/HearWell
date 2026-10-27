"""The Q&A assistant, FAQ version (spec #396).

Its questions and answers are written in content.py, not a table (ADR 0033): changing one is a
PR, and the owner merging it is the review. It answers general questions only, the same for
everyone, and never reads anyone's records (ADR 0032).
"""
