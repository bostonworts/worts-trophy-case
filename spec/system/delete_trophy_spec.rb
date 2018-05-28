require "rails_helper"

describe "deleting a trophy" do
  it "works when user clicks to delete their own trophy" do
    worts_member = create(:user)
    trophy = create(:trophy, user: worts_member)

    login_as(worts_member)

    click_on "Trophies"

    expect(page).to have_content(trophy.bjcp_score)

    click_link "Delete Trophy"

    expect(page).to have_content("Trophy successfully deleted")
    expect(page).not_to have_content(trophy.bjcp_score)
  end

  it "doesn't render a link to delete other people's trophies" do
    # not this user's trophy
    trophy = create(:trophy)
    worts_member = create(:user)

    login_as(worts_member)

    click_on "Trophies"

    expect(page).to have_content(trophy.bjcp_score)
    expect(page).not_to have_link("Delete Trophy")
  end
end
