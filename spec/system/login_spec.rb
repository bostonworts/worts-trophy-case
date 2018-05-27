require "rails_helper"

describe "logging in" do
  it "doesn't email a magic link to non-worts member" do
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
