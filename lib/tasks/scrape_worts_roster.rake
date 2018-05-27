desc "Scrape the worts roster to keep the users table up to date"
task scrape_worts_roster: :environment do
  require "capybara"

  session = Capybara::Session.new(:selenium_chrome_headless)
  session.visit "https://davidtodd.info/cgi-bin/mailman/listinfo/wort"

  session.fill_in("roster-email", with: ENV.fetch("WORTS_LIST_USERNAME"))
  session.fill_in("roster-pw", with: ENV.fetch("WORTS_LIST_PASSWORD"))
  session.find("input[name='SubscriberRoster']").click

  roster_list_doc = Nokogiri::HTML(session.html)
  emails_with_spaces = roster_list_doc.css("tr li a").map(&:text)
  actual_emails = emails_with_spaces.map do |email_with_spaces|
    # Convert "foo at example.com" to "foo@example.com"
    email_with_spaces.gsub(" at ", "@")
  end

  if actual_emails.count > 100
    # Assume the scraping went wrong if there are less than 100 emails
    result = WortMembersUpdater.update(subscribed_emails: actual_emails)
    puts result
  end
end
