import csv
import io


def _tags_to_string(tags_arr):
    tags_str = ""
    for tag in tags_arr:
        tags_str += f"{tag['namespace']}/{tag['key']}:{tag['value']};"

    tags_str = tags_str[:-1]
    return f"{tags_str}"


def export_csv_header(fieldnames):
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
    writer.writerow(fieldnames)
    return output.getvalue()


def export_host_to_csv_row(host, fieldnames):
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
    row = {**host, "tags": _tags_to_string(host.get("tags", []))}
    writer.writerow([row.get(field, "") for field in fieldnames])
    return output.getvalue()
