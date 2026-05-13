#!/bin/bash


export KIROKU_DATABASE_URL="postgresql+psycopg://bmu:bmu@localhost:5432/bmu"
export KIROKU_DATABASE_URL_SYNC="postgresql+psycopg://bmu:bmu@localhost:5432/bmu"
export KIROKU_REDIS_URL="redis://localhost:6379/0" 
export KIROKU_RELOAD=TRUE 
export KIROKU_WEB_WORKERS=1
kiroku serve
    
