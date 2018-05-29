class Medal
  def initialize(place, place_context)
    @place = place
    @place_context = place_context
  end

  def description
    "#{context_description} #{place_description}"
  end

  def icon
    if place_context == "category"
      case place
      when 1 then "🥇"
      when 2 then "🥈"
      when 3 then "🥉"
      when 4 then "🏅"
      end
    elsif place_context == "best_of_show"
      "🏆"
    end
  end

  private

  attr_reader :place, :place_context

  def context_description
    case place_context
    when "category" then "Category"
    when "best_of_show" then "Best of Show"
    else raise "place_context not handled: #{place_context}"
    end
  end

  def place_description
    case place
    when 1 then "Gold"
    when 2 then "Silver"
    when 3 then "Bronze"
    when 4 then "Honorable Mention"
    end
  end
end
