require "rails_helper"

describe "submit trophy" do
  it "succeeds with required fields after logging in via email" do
    visit "/"

    click_link "Add Trophy"

    # Submit login form with email address in worts list
    expect(page).to have_content "We'll send you a magic link to the email you use for the Boston Wort Processors email list"

    # Open email, visit link in email to log in
    # Assert we were redirected back to "Submit Trophy" form
    # Submit trophy form with required fields
    # Assert the trophy shows up in the trophy case table
  end
end
