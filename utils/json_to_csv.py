import csv
import io


def _tags_to_string(tags_arr):
    tags_str = ""
    for tag in tags_arr:
        tags_str += f'{tag["namespace"]}/{tag["key"]}:{tag["value"]};'

    tags_str = tags_str[:-1]
    return f"{tags_str}"


def json_arr_to_csv(json_arr_data):
    # Prepare a buffer to store the CSV data
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
    writer.writerow(json_arr_data[0].keys())
    for host in json_arr_data:
        host["tags"] = _tags_to_string(host["tags"])
        # Write the data row
        writer.writerow(host.values())

    # Get the CSV string from the buffer
    csv_string = output.getvalue()

    return csv_string
