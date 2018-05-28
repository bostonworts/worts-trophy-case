require "rails_helper"

describe "Creating a competition" do
  it "succeeds for a worts member with required fields" do
    worts_member = create(:user)
    login_as(worts_member)

    click_link "Add Competition"

    fill_in :competition_name, with: "Boss Hop"
    fill_in :competition_url, with: "http://ipa.wort.org"

    select "2018", from: :competition_date_1i
    select "January", from: :competition_date_2i
    select "28", from: :competition_date_3i

    click_on "Create Competition"

    expect(page).to have_content "Competition successfully created"

    click_link "Add Trophy"
    expect(page).to have_select :trophy_competition_id, options: ["2018: Boss Hop"]
  end
end
