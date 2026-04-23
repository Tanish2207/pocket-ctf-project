#!/bin/bash
while true; do
  echo "Running port scan..."
  nmap -sS victim        
  echo "Running ICMP flood..."
  ping -c 10 victim
  echo "Sleeping 45 seconds..."
  sleep 45
done