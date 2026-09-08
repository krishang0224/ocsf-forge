"""Separate SQL syntax from quoted values and comments for console checks."""


def scrub_sql(statement: str) -> str:
    output = []
    index = 0
    while index < len(statement):
        char = statement[index]
        if char in {"'", '"'}:
            quote = char
            index += 1
            while index < len(statement):
                if statement[index] == quote:
                    if index + 1 < len(statement) and statement[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                raise ValueError("Unterminated SQL quote")
            output.append(" ")
        elif statement.startswith("--", index):
            end = statement.find("\n", index)
            index = len(statement) if end < 0 else end + 1
            output.append(" ")
        elif statement.startswith("/*", index):
            depth = 1
            index += 2
            while index < len(statement) and depth:
                if statement.startswith("/*", index):
                    depth += 1
                    index += 2
                elif statement.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise ValueError("Unterminated SQL comment")
            output.append(" ")
        else:
            output.append(char)
            index += 1
    return "".join(output)
