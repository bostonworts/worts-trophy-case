desc "Load the worts roster from Google Sheets to keep the users table up to date"
task load_worts_roster: :environment do
  puts "Updating worts roster from Google Sheet"

  config = StringIO.new(ENV.fetch("WORTS_ROSTER_GDRIVE_BOT_CONFIG_JSON"))
  worts_roster_spreadsheet_key = ENV.fetch("WORTS_ROSTER_SPREADSHEET_KEY")

  session = GoogleDrive::Session.from_service_account_key(config)
  ws = session.spreadsheet_by_key(worts_roster_spreadsheet_key).worksheets[0]

  NAME_COLUMN = 3
  PAYPAL_EMAIL_COLUMN = 4
  LIST_EMAIL_COLUMN = 5

  FIRST_ACTUAL_ROW = 3

  members = (FIRST_ACTUAL_ROW..ws.num_rows).map do |row|
    # Try to get list_email first
    # Fall back to paypal_email
    list_email = ws[row, LIST_EMAIL_COLUMN].presence || ws[row, PAYPAL_EMAIL_COLUMN].presence
    name = ws[row, NAME_COLUMN]
    { list_email: list_email.downcase, name: name }
  end

  counts = { created: 0, updated: 0, untouched: 0 }

  members.each do |member|
    list_email = member[:list_email]
    name = member[:name]

    user = User.find_by(email: list_email)
    if user
      if user.has_default_name?
        puts "Trophy case name not yet set, setting name to #{name}"
        user.update!(full_name: name)
        counts[:updated] += 1
      else
        puts "Trophy case name already set: #{user.full_name}"
        counts[:untouched] += 1
      end
    else
      puts "Member #{list_email} not found, creating User record"
      User.create!(
        admin: false,
        email: list_email,
        full_name: name,
      )
      counts[:created] += 1
    end
  end

  counts.each do |key, count|
    puts "Done: #{key} #{count} User records"
  end
end
