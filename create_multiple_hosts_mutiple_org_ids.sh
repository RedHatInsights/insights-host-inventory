#!/bin/bash

# Script to loop a specified number of times and run a make command with arguments.

# Validate that iterations is a positive integer
if ! [[ "$iterations" =~ ^[0-9]+$ ]]; then
  echo "Error: <number_of_org_ids> must be a positive integer."
  echo "Usage: $0 <number_of_org_ids> [run_inv_mq_service_test_producer] [make_argument1=value1 ...]"
  exit 1
fi
# Shift the first argument (iterations) so that $@ contains only the make arguments
shift

# Check if there are any arguments for make
if [ $# -eq 0 ]; then
  echo "Warning: No arguments provided for the 'make' command."
  echo "Make will be called without any targets or variables."
fi

# Loop from 1 to the specified number of iterations
for i in $(seq 1 "$iterations")
do
  echo "------------------------------------"
  echo "Iteration $i of $iterations"
  echo "Running: make $@ NUM_OF_DIFF_ORG_IDS=$i"
  echo "------------------------------------"

  # Run the make command with all remaining arguments
  make "$@" NUM_OF_DIFF_ORG_IDS=$i

    # Check the exit status of the make command
  if [ $? -ne 0 ]; then
    echo "Error: 'make $@' failed on iteration $i"
    # Decide if you want to exit the script on failure or continue
    # exit 1 # Uncomment to exit on failure
  fi
  echo "" # Add a newline for better readability
done

echo "------------------------------------"
echo "Script finished."
echo "------------------------------------"
