require "rails_helper"

describe "logging in" do
  it "doesn't email a magic link to non-worts member" do
    visit "/"

    click_link "Trophies"
    click_on "Add Trophy"

    # Submit login form with email address in worts list
    expect(current_path).to eq("/users/sign_in")

    fill_in "Worts email", with: "notamember@example.com"
    click_on "Send magic link"

    emails = ActionMailer::Base.deliveries
    expect(emails).not_to be_empty
  end

  it "doesn't email a magic link to deactivated worts member" do
    deactivated_user = create(:user, :deactivated)
    login_as(deactivated_user)

    expect(page).to have_content("It looks like #{deactivated_user.email} is no longer a Boston Worts member.")
  end
end
