$DB = "$HOME/.evemisslab/pmw-fabric/pmw.sqlite3"
eml-pmw --db $DB agent-add user:neo --kind human --display-name "Neo.K"
eml-pmw --db $DB workspace-create "Shared Research Canvas" --created-by user:neo --id pmw-ws-research-001
# Import already-bound Herdr semantic identities from the same or an existing bridge DB:
eml-pmw --db $DB import-herdr agent://evemisslab/research/claude-main --bridge-db $DB
