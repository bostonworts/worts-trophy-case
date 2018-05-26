require "rails_helper"

describe "submit trophy" do
  it "succeeds with required fields after logging in via email" do
    worts_member = create(:user)

    visit "/"

    click_link "Add Trophy"

    # Submit login form with email address in worts list
    expect(current_path).to eq("/users/sign_in")

    fill_in "Worts email", with: worts_member.email
    click_on "Send magic link"

    # Open email, visit link in email to log in
    emails = ActionMailer::Base.deliveries
    expect(emails.size).to eq(1)

    magic_link_url = emails.first.body.raw_source.match(/http:\/\/[\S]+/)

    visit magic_link_url

    # It redirects to root in test because the session is cleared out
    # In development, it redirects you back to where you wanted to go initially
    click_link "Add Trophy"

    # Now we're logged in so it doesn't redirect
    expect(current_path).to eq("/trophies/new")

    fill_in :trophy_bjcp_score, with: 25

    competition_date = Date.yesterday
    select competition_date.year, from: :trophy_competition_date_1i
    select competition_date.strftime("%B"), from: :trophy_competition_date_2i
    select competition_date.day, from: :trophy_competition_date_3i

    fill_in :trophy_competition_url, with: "http://bhc.wort.org"

    click_on "Create Trophy"

    expect(current_path).to eq("/")

    # Brewer should be in the trophy list now
    expect(page).to have_content(worts_member.full_name)
  end

  it "doesn't send magic link to non-worts member" do
    visit "/"

    click_link "Add Trophy"

    # Submit login form with email address in worts list
    expect(current_path).to eq("/users/sign_in")

    fill_in "Worts email", with: "notamember@example.com"
    click_on "Send magic link"

    emails = ActionMailer::Base.deliveries
    expect(emails).to be_empty
  end
end
